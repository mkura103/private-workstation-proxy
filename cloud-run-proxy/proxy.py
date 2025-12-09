#!/usr/bin/env python3
"""
Cloud Run Proxy Server for Private Cloud Workstations
- Workstation APIからアクセストークンを取得
- Workstationに認証付きでリクエストをプロキシ
- WebSocket対応
"""

import os
import asyncio
import time
import aiohttp
from aiohttp import web, WSMsgType
import ssl
import sys
import secrets

# 標準出力をバッファリングしない
sys.stdout.reconfigure(line_buffering=True)

# 環境変数
CLUSTER_HOSTNAME = os.environ.get('CLUSTER_HOSTNAME', 'cluster-xxx.cloudworkstations.dev')
PROJECT_ID = os.environ.get('PROJECT_ID', 'kura-project-1')
REGION = os.environ.get('REGION', 'asia-northeast1')
CLUSTER_NAME = os.environ.get('CLUSTER_NAME', 'workstation-cluster')
CONFIG_NAME = os.environ.get('CONFIG_NAME', 'workstation-config')
PORT = int(os.environ.get('PORT', '8080'))
AUTH_MODE = os.environ.get('AUTH_MODE', 'password')  # 'password' or 'iap'
PROXY_PASSWORD = os.environ.get('PROXY_PASSWORD', 'changeme')

# メタデータサーバーURL
METADATA_TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"

# トークンキャッシュ
_gcp_token_cache = {"token": None, "expires": 0}
_ws_token_cache = {}  # {workstation_name: {"token": ..., "expires": ...}}

# セッション管理
_sessions = {}  # {session_id: {"expires": timestamp, "last_workstation": str}}
SESSION_DURATION = 86400  # 24時間


def get_last_workstation(request) -> str:
    """セッションから最後にアクセスしたWorkstation名を取得"""
    session_id = request.cookies.get('session')
    if session_id and session_id in _sessions:
        return _sessions[session_id].get('last_workstation')
    return None


def set_last_workstation(request, ws_name: str):
    """セッションに最後にアクセスしたWorkstation名を保存"""
    session_id = request.cookies.get('session')
    if session_id and session_id in _sessions:
        _sessions[session_id]['last_workstation'] = ws_name

# ステータスページHTML（CSSの {} は {{}} にエスケープ）
STATUS_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workstation Status</title>
    <style>
        body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
        .status-box {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); min-width: 300px; }}
        h1 {{ margin-top: 0; font-size: 1.5rem; }}
        .info {{ margin: 1rem 0; }}
        .label {{ color: #666; font-size: 0.9rem; }}
        .value {{ font-size: 1.1rem; font-weight: bold; }}
        .state-running {{ color: #34a853; }}
        .state-stopped {{ color: #ea4335; }}
        .state-starting, .state-stopping {{ color: #fbbc04; }}
        .state-other {{ color: #666; }}
        button {{ padding: 0.75rem 1.5rem; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; margin-top: 1rem; }}
        .btn-start {{ background: #34a853; color: white; }}
        .btn-start:hover {{ background: #2d8f47; }}
        .btn-stop {{ background: #ea4335; color: white; }}
        .btn-stop:hover {{ background: #d33426; }}
        .btn-disabled {{ background: #ccc; color: #666; cursor: not-allowed; }}
        .error {{ color: red; font-size: 0.9rem; margin-top: 1rem; }}
        .message {{ color: #34a853; font-size: 0.9rem; margin-top: 1rem; }}
        a {{ color: #4285f4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="status-box">
        <h1>Workstation Status</h1>
        <div class="info">
            <div class="label">Name</div>
            <div class="value">{workstation}</div>
        </div>
        <div class="info">
            <div class="label">State</div>
            <div class="value {state_class}">{state}</div>
        </div>
        <div class="info">
            <div class="label">Host</div>
            <div class="value" style="font-size: 0.9rem;">{host}</div>
        </div>
        {error}
        {message}
        {button}
        {open_link}
    </div>
</body>
</html>
"""

# ログインページHTML（CSSの {} は {{}} にエスケープ）
LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workstation Proxy Login</title>
    <style>
        body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
        .login-box {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ margin-top: 0; font-size: 1.5rem; }}
        input {{ display: block; width: 100%; padding: 0.5rem; margin: 0.5rem 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }}
        button {{ width: 100%; padding: 0.5rem; background: #4285f4; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        button:hover {{ background: #3367d6; }}
        .error {{ color: red; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Workstation Proxy</h1>
        {error}
        <form method="POST" action="/login">
            <input name="password" type="password" placeholder="Password" required autofocus>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""


def log(msg):
    """ログ出力"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def parse_workstation_path(path: str) -> tuple:
    """
    パスからWorkstation名と実際のパスを抽出
    /ws/alice/foo/bar → ("alice", "/foo/bar")
    /health → (None, "/health")
    """
    if path.startswith("/ws/"):
        parts = path[4:].split("/", 1)
        ws_name = parts[0]
        actual_path = "/" + parts[1] if len(parts) > 1 else "/"
        return ws_name, actual_path
    return None, path


async def get_gcp_access_token() -> str:
    """メタデータサーバーからGCPアクセストークンを取得"""
    global _gcp_token_cache

    # キャッシュが有効なら返す
    if _gcp_token_cache["token"] and time.time() < _gcp_token_cache["expires"] - 60:
        return _gcp_token_cache["token"]

    headers = {"Metadata-Flavor": "Google"}
    async with aiohttp.ClientSession() as session:
        async with session.get(METADATA_TOKEN_URL, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                _gcp_token_cache["token"] = data["access_token"]
                _gcp_token_cache["expires"] = time.time() + data.get("expires_in", 3600)
                return data["access_token"]
            else:
                raise Exception(f"Failed to get GCP token: {resp.status}")


async def get_workstation_access_token(workstation_name: str) -> str:
    """Workstation APIからアクセストークンを取得"""
    global _ws_token_cache

    # Workstation名ごとにキャッシュをチェック（5分のマージン）
    cache = _ws_token_cache.get(workstation_name, {"token": None, "expires": 0})
    if cache["token"] and time.time() < cache["expires"] - 300:
        return cache["token"]

    # GCPアクセストークン取得
    gcp_token = await get_gcp_access_token()

    # Workstation API呼び出し
    api_url = (
        f"https://workstations.googleapis.com/v1/projects/{PROJECT_ID}/"
        f"locations/{REGION}/workstationClusters/{CLUSTER_NAME}/"
        f"workstationConfigs/{CONFIG_NAME}/workstations/{workstation_name}:generateAccessToken"
    )

    headers = {
        "Authorization": f"Bearer {gcp_token}",
        "Content-Type": "application/json"
    }

    # 1時間後に期限切れ
    expire_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    body = {"expireTime": expire_time}

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json=body) as resp:
            if resp.status == 200:
                data = await resp.json()
                _ws_token_cache[workstation_name] = {
                    "token": data["accessToken"],
                    "expires": time.time() + 3600
                }
                log(f"Got Workstation access token for '{workstation_name}', expires: {data.get('expireTime')}")
                return data["accessToken"]
            else:
                error = await resp.text()
                raise Exception(f"Failed to get Workstation token for '{workstation_name}': {resp.status} - {error}")


async def get_workstation_status(workstation_name: str) -> dict:
    """Workstation APIから状態を取得"""
    # GCPアクセストークン取得
    gcp_token = await get_gcp_access_token()

    # Workstation API呼び出し
    api_url = (
        f"https://workstations.googleapis.com/v1/projects/{PROJECT_ID}/"
        f"locations/{REGION}/workstationClusters/{CLUSTER_NAME}/"
        f"workstationConfigs/{CONFIG_NAME}/workstations/{workstation_name}"
    )

    headers = {
        "Authorization": f"Bearer {gcp_token}",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {
                    "workstation": workstation_name,
                    "state": data.get("state", "UNKNOWN"),
                    "host": f"{workstation_name}.{CLUSTER_HOSTNAME}"
                }
            elif resp.status == 404:
                return {
                    "workstation": workstation_name,
                    "state": "NOT_FOUND",
                    "error": "Workstation not found"
                }
            else:
                error = await resp.text()
                return {
                    "workstation": workstation_name,
                    "state": "ERROR",
                    "error": f"API error: {resp.status} - {error}"
                }


async def start_workstation(workstation_name: str) -> dict:
    """Workstationを開始"""
    gcp_token = await get_gcp_access_token()

    api_url = (
        f"https://workstations.googleapis.com/v1/projects/{PROJECT_ID}/"
        f"locations/{REGION}/workstationClusters/{CLUSTER_NAME}/"
        f"workstationConfigs/{CONFIG_NAME}/workstations/{workstation_name}:start"
    )

    headers = {
        "Authorization": f"Bearer {gcp_token}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json={}) as resp:
            if resp.status == 200:
                log(f"Workstation '{workstation_name}' start initiated")
                return {"success": True}
            else:
                error = await resp.text()
                log(f"Failed to start workstation '{workstation_name}': {resp.status} - {error}")
                return {"success": False, "error": f"API error: {resp.status}"}


async def stop_workstation(workstation_name: str) -> dict:
    """Workstationを停止"""
    gcp_token = await get_gcp_access_token()

    api_url = (
        f"https://workstations.googleapis.com/v1/projects/{PROJECT_ID}/"
        f"locations/{REGION}/workstationClusters/{CLUSTER_NAME}/"
        f"workstationConfigs/{CONFIG_NAME}/workstations/{workstation_name}:stop"
    )

    headers = {
        "Authorization": f"Bearer {gcp_token}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json={}) as resp:
            if resp.status == 200:
                log(f"Workstation '{workstation_name}' stop initiated")
                return {"success": True}
            else:
                error = await resp.text()
                log(f"Failed to stop workstation '{workstation_name}': {resp.status} - {error}")
                return {"success": False, "error": f"API error: {resp.status}"}


async def handle_status(request):
    """Workstationのステータスページを表示"""
    ws_name = request.match_info.get('name')
    if not ws_name:
        return web.Response(status=400, text="Workstation name required")

    message = ""
    error_msg = ""

    # POST: 開始/停止アクション
    if request.method == 'POST':
        data = await request.post()
        action = data.get('action')

        if action == 'start':
            result = await start_workstation(ws_name)
            if result.get('success'):
                message = '<div class="message">Starting workstation... (refresh in a few seconds)</div>'
            else:
                error_msg = f'<div class="error">Failed to start: {result.get("error", "Unknown error")}</div>'
        elif action == 'stop':
            result = await stop_workstation(ws_name)
            if result.get('success'):
                message = '<div class="message">Stopping workstation... (refresh in a few seconds)</div>'
            else:
                error_msg = f'<div class="error">Failed to stop: {result.get("error", "Unknown error")}</div>'

    log(f"Status page for workstation: {ws_name}")
    status = await get_workstation_status(ws_name)

    state = status.get('state', 'UNKNOWN')

    # 状態に応じたCSSクラス
    if state == 'STATE_RUNNING':
        state_class = 'state-running'
    elif state == 'STATE_STOPPED':
        state_class = 'state-stopped'
    elif state in ['STATE_STARTING', 'STATE_STOPPING']:
        state_class = 'state-starting'
    else:
        state_class = 'state-other'

    # ボタン生成
    if state == 'STATE_RUNNING':
        button = f'''<form method="POST">
            <input type="hidden" name="action" value="stop">
            <button type="submit" class="btn-stop">Stop Workstation</button>
        </form>'''
    elif state == 'STATE_STOPPED':
        button = f'''<form method="POST">
            <input type="hidden" name="action" value="start">
            <button type="submit" class="btn-start">Start Workstation</button>
        </form>'''
    elif state in ['STATE_STARTING', 'STATE_STOPPING']:
        button = '<button class="btn-disabled" disabled>Processing...</button>'
    else:
        button = ''

    # エラー表示
    if status.get('error') and not error_msg:
        error_msg = f'<div class="error">{status["error"]}</div>'

    # STATE_RUNNINGの時のみWorkstationへのリンクを表示
    if state == 'STATE_RUNNING':
        open_link = f'<div style="margin-top: 1.5rem; font-size: 0.9rem;"><a href="/ws/{ws_name}/">Open Workstation</a></div>'
    else:
        open_link = ''

    html = STATUS_HTML.format(
        workstation=ws_name,
        state=state,
        state_class=state_class,
        host=status.get('host', ''),
        error=error_msg,
        message=message,
        button=button,
        open_link=open_link
    )
    return web.Response(text=html, content_type='text/html')


async def health_check(request):
    """ヘルスチェックエンドポイント"""
    return web.Response(text="OK")


async def login_page(request):
    """ログインページを表示"""
    error_msg = ""
    if request.query.get('error'):
        error_msg = '<p class="error">Invalid password</p>'
    html = LOGIN_HTML.format(error=error_msg)
    return web.Response(text=html, content_type='text/html')


async def handle_login(request):
    """ログイン処理"""
    data = await request.post()
    password = data.get('password', '')

    if password == PROXY_PASSWORD:
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = {"expires": time.time() + SESSION_DURATION}
        log(f"Login successful, session created")

        # ログイン後のリダイレクト先
        redirect_to = request.query.get('next', '/')
        response = web.HTTPFound(redirect_to)
        response.set_cookie('session', session_id, httponly=True, max_age=SESSION_DURATION)
        return response

    log(f"Login failed: invalid password")
    return web.HTTPFound('/login?error=1')


async def handle_logout(request):
    """ログアウト処理"""
    session_id = request.cookies.get('session')
    if session_id and session_id in _sessions:
        del _sessions[session_id]
        log(f"Session logged out")

    response = web.HTTPFound('/login')
    response.del_cookie('session')
    return response


def is_authenticated(request) -> bool:
    """セッションが有効かチェック"""
    session_id = request.cookies.get('session')
    if not session_id:
        return False

    session = _sessions.get(session_id)
    if not session:
        return False

    if time.time() > session.get('expires', 0):
        # 期限切れセッションを削除
        del _sessions[session_id]
        return False

    return True


@web.middleware
async def auth_middleware(request, handler):
    """認証ミドルウェア"""
    # IAPモードなら認証スキップ（IAP or gcloud proxyで認証済み前提）
    if AUTH_MODE == 'iap':
        return await handler(request)

    # 認証不要なパス
    if request.path in ['/health', '/login'] or request.path.startswith('/status/'):
        return await handler(request)

    # 認証チェック
    if not is_authenticated(request):
        # ログインページにリダイレクト（元のパスを保存）
        redirect_url = f'/login?next={request.path}'
        return web.HTTPFound(redirect_url)

    return await handler(request)


async def handle_websocket(request):
    """WebSocketプロキシ"""
    log(f"WebSocket connection request: {request.path}")

    # パスからWorkstation名を抽出
    ws_name, actual_path = parse_workstation_path(request.path)

    # /ws/{name}/ 以外のパスの場合、セッションから最後のWorkstation名を取得
    if ws_name is None:
        ws_name = get_last_workstation(request)
        actual_path = request.path  # パスはそのまま使用
        if ws_name is None:
            log("WebSocket: Workstation name not found in path or session")
            return web.Response(status=400, text="Workstation name required. Use /ws/{name}/...")

    # Workstationホスト名を動的に構築
    workstation_host = f"{ws_name}.{CLUSTER_HOSTNAME}"

    ws_server = web.WebSocketResponse()
    await ws_server.prepare(request)
    log("WebSocket server prepared")

    try:
        # Workstationアクセストークン取得
        token = await get_workstation_access_token(ws_name)
        log(f"Got workstation token for WebSocket ({ws_name})")

        # Workstationへの接続URL
        path = actual_path
        if request.query_string:
            path = f"{path}?{request.query_string}"
        ws_url = f"wss://{workstation_host}{path}"
        log(f"Connecting to WebSocket: {ws_url}")

        # ヘッダー準備（元のリクエストからCookie等を転送）
        headers = {
            "Authorization": f"Bearer {token}",
            "Host": workstation_host,
            # Originを正しいWorkstationホストに設定（重要）
            "Origin": f"https://{workstation_host}",
        }

        # Cookieを転送
        if 'Cookie' in request.headers:
            headers['Cookie'] = request.headers['Cookie']

        # User-Agent, Sec-WebSocket-Protocolを転送（Originは上で設定済み）
        for h in ['User-Agent', 'Sec-WebSocket-Protocol']:
            if h in request.headers:
                headers[h] = request.headers[h]

        log(f"WebSocket headers: {list(headers.keys())}")

        ssl_context = ssl.create_default_context()
        timeout = aiohttp.ClientTimeout(total=3600)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            log("Attempting WebSocket connection to workstation...")
            async with session.ws_connect(
                ws_url,
                headers=headers,
                ssl=ssl_context,
                heartbeat=30
            ) as ws_client:
                log("WebSocket connected to workstation!")

                async def forward_to_client():
                    try:
                        async for msg in ws_client:
                            if msg.type == WSMsgType.TEXT:
                                await ws_server.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await ws_server.send_bytes(msg.data)
                            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                                log("WebSocket client closed")
                                break
                            elif msg.type == WSMsgType.ERROR:
                                log(f"WebSocket client error: {ws_client.exception()}")
                                break
                    except Exception as e:
                        log(f"Error forwarding to client: {e}")

                async def forward_to_server():
                    try:
                        async for msg in ws_server:
                            if msg.type == WSMsgType.TEXT:
                                await ws_client.send_str(msg.data)
                            elif msg.type == WSMsgType.BINARY:
                                await ws_client.send_bytes(msg.data)
                            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                                log("WebSocket server closed")
                                break
                            elif msg.type == WSMsgType.ERROR:
                                log(f"WebSocket server error: {ws_server.exception()}")
                                break
                    except Exception as e:
                        log(f"Error forwarding to server: {e}")

                # 両方向のプロキシを並行実行
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_to_client()),
                        asyncio.create_task(forward_to_server())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # 残りのタスクをキャンセル
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    except aiohttp.WSServerHandshakeError as e:
        log(f"WebSocket handshake error: {e}")
    except Exception as e:
        log(f"WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if not ws_server.closed:
            await ws_server.close()
        log("WebSocket connection closed")

    return ws_server


async def handle_request(request):
    """HTTPリクエストプロキシ"""

    # WebSocketアップグレードの確認
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return await handle_websocket(request)

    # パスからWorkstation名を抽出
    ws_name, actual_path = parse_workstation_path(request.path)

    # /ws/{name}/ 以外のパスの場合、セッションから最後のWorkstation名を取得
    if ws_name is None:
        ws_name = get_last_workstation(request)
        actual_path = request.path  # パスはそのまま使用
        if ws_name is None:
            return web.Response(status=400, text="Workstation name required. Use /ws/{name}/...")
    else:
        # Workstation名をセッションに保存
        set_last_workstation(request, ws_name)

    # Workstationホスト名を動的に構築
    workstation_host = f"{ws_name}.{CLUSTER_HOSTNAME}"

    log(f"HTTP {request.method} {request.path} -> {workstation_host}{actual_path}")

    try:
        # Workstationアクセストークン取得
        token = await get_workstation_access_token(ws_name)

        # プロキシ先URL
        path = actual_path
        if request.query_string:
            path = f"{path}?{request.query_string}"
        target_url = f"https://{workstation_host}{path}"

        # ヘッダー準備
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ('host', 'transfer-encoding', 'content-length', 'authorization'):
                headers[key] = value

        headers['Authorization'] = f"Bearer {token}"
        headers['Host'] = workstation_host

        # リクエストボディ
        body = await request.read()

        ssl_context = ssl.create_default_context()
        timeout = aiohttp.ClientTimeout(total=3600)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body if body else None,
                ssl=ssl_context,
                allow_redirects=False
            ) as resp:
                # レスポンスヘッダー
                response_headers = {}
                for key, value in resp.headers.items():
                    if key.lower() not in ('transfer-encoding', 'content-encoding', 'content-length'):
                        # Locationヘッダーの書き換え
                        if key.lower() == 'location':
                            if workstation_host in value:
                                value = value.replace(f"https://{workstation_host}", f"/ws/{ws_name}")
                            # Google認証ページへのリダイレクトも抑制
                            if "workstations.cloud.google.com" in value:
                                log(f"Blocked redirect to: {value}")
                                continue
                        response_headers[key] = value

                # レスポンスボディ
                body = await resp.read()

                return web.Response(
                    status=resp.status,
                    headers=response_headers,
                    body=body
                )

    except Exception as e:
        log(f"Proxy error: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=502, text=f"Proxy Error: {e}")


def create_app():
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_route('GET', '/health', health_check)
    app.router.add_route('*', '/status/{name}', handle_status)
    app.router.add_route('GET', '/login', login_page)
    app.router.add_route('POST', '/login', handle_login)
    app.router.add_route('GET', '/logout', handle_logout)
    app.router.add_route('*', '/{path:.*}', handle_request)
    return app


if __name__ == '__main__':
    log(f"Starting proxy server on port {PORT}")
    log(f"Cluster hostname: {CLUSTER_HOSTNAME}")
    log(f"Project: {PROJECT_ID}, Region: {REGION}")
    log(f"Cluster: {CLUSTER_NAME}, Config: {CONFIG_NAME}")
    if AUTH_MODE == 'iap':
        log(f"Authentication: IAP mode (no password)")
    else:
        log(f"Authentication: password mode")
    log("Usage: /ws/{workstation_name}/...")
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=PORT)
