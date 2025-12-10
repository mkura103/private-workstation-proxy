# Cloud Run Proxy Server

Private Cloud WorkstationsへアクセスするためのPython (aiohttp) リバースプロキシをCloud Runで実行。

## 構成

```
[インターネット]
    ↓ HTTPS
[Cloud Run (Python aiohttp)] ← IAP認証 (Googleログイン)
    ↓ Direct VPC Egress
[Private Workstations]
```

## ファイル構成

| ファイル | 説明 |
|----------|------|
| `proxy.py` | aiohttp WebSocket対応プロキシ (メイン) |
| `Dockerfile` | Pythonコンテナイメージ |
| `requirements.txt` | Python依存関係 (aiohttp) |
| `main.tf` | Terraform (Cloud Run, Artifact Registry) |
| `variables.tf` | Terraform変数定義 |
| `outputs.tf` | Terraform出力定義 |
| `terraform.tfvars` | 設定値 (gitignore対象) |
| `terraform.tfvars.example` | 設定テンプレート |
| `gethostname.sh` | cluster_hostname 取得・更新スクリプト |
| `localhost_access.sh` | ローカルプロキシ起動スクリプト (IAM認証用) |

## 使用方法

### デプロイ

```bash
# 設定ファイル作成
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

# workstations から cluster_hostname を取得
./gethostname.sh

# デプロイ
terraform init
terraform apply
```

### 削除

```bash
terraform destroy
```

### アクセス

```
# ブラウザで直接アクセス (Googleログイン)
https://SERVICE_URL/status/dev-workstation
https://SERVICE_URL/ws/dev-workstation/
```

## 認証

Cloud Run に IAP を有効化し、Googleログインで認証。
`terraform apply` 時に IAP 有効化と IAP アクセス権付与が自動実行される。

```hcl
iap_users = ["user:alice@example.com"]
```

- ブラウザから直接 Cloud Run URL にアクセス可能
- Googleアカウントで認証
- IAP設定はサービス更新時に自動的に再適用される

## 複数Workstation対応

パスベースルーティング:

```
/ws/alice/ → alice のWorkstation
/ws/bob/   → bob のWorkstation
```

セッションベースで最後にアクセスしたWorkstationを記憶。
静的リソース (CSS, JS等) も正しくルーティング。

## Workstation状態管理

`/status/{workstation-name}` でWorkstationの状態確認・開始/停止が可能:

```
https://SERVICE_URL/status/dev-workstation
```

### 機能

| 機能 | 説明 |
|------|------|
| 状態表示 | STATE_RUNNING (緑), STATE_STOPPED (赤), STATE_STARTING/STOPPING (黄) |
| 開始ボタン | STATE_STOPPEDの時に表示、クリックでWorkstation開始 |
| 停止ボタン | STATE_RUNNINGの時に表示、クリックでWorkstation停止 |
| Open Workstationリンク | STATE_RUNNINGの時のみ `/ws/{name}/` へのリンク表示 |
| 自動リロード | 15秒ごとに自動更新（状態変化を監視） |
| 重複操作防止 | 遷移中（STARTING/STOPPING）はボタン無効化、409エラーは無視 |

### Workstation API

```
GET  /v1/.../workstations/{name}       # 状態取得
POST /v1/.../workstations/{name}:start # 開始
POST /v1/.../workstations/{name}:stop  # 停止
```

## 認証フロー

```
1. ユーザー → Cloud Run URL にアクセス
2. IAP → Googleログイン認証 (自動)
3. Cloud Run → メタデータサーバー → GCPアクセストークン取得
4. Cloud Run → Workstation API (generateAccessToken) → Workstationトークン取得
5. Cloud Run → Workstation (Authorization: Bearer TOKEN)
```

## 技術仕様

### WebSocket対応

- 双方向プロキシ (asyncio.wait + FIRST_COMPLETED)
- Originヘッダーを正しいWorkstationホストに設定
- Cookie, User-Agent, Sec-WebSocket-Protocol 転送
- heartbeat: 30秒

### セッション管理

- 自動的にセッションを初期化
- 静的リソースルーティングのために `last_workstation` を記憶
- セッション有効期限: 24時間

### タイムアウト設定

| 項目 | 値 |
|------|--------|
| Cloud Run timeout | 3600秒 (60分) |
| aiohttp ClientTimeout | 3600秒 |

### Direct VPC Egress

VPC Connectorを使わず、Cloud Runから直接VPCに接続。

```hcl
vpc_access {
  network_interfaces {
    network    = "default"
    subnetwork = "default"
  }
  egress = "ALL_TRAFFIC"
}
```

## 環境変数

Cloud Run に設定される環境変数:

| 変数 | 説明 |
|------|------|
| `PROJECT_ID` | GCPプロジェクトID |
| `REGION` | リージョン |
| `CLUSTER_HOSTNAME` | Workstationクラスターホスト名 |

## Terraform変数

| 変数 | 説明 | デフォルト |
|------|------|------------|
| `project_id` | GCPプロジェクトID | (必須) |
| `region` | リージョン | asia-northeast1 |
| `service_name` | Cloud Runサービス名 | workstation-proxy |
| `network` | VPCネットワーク名 | default |
| `subnet` | サブネット名 | default |
| `cluster_hostname` | Workstationクラスターホスト名 | (必須) |
| `iap_users` | IAMユーザーリスト | [] |

## 60分制限の対応

Cloud Runの最大タイムアウトは60分。長時間の開発作業には以下の対応が必要:

1. ブラウザをリロードして再接続
2. VS Code IDE は自動再接続をサポート
