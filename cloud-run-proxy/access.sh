#!/bin/bash
# Cloud Run Proxy Server アクセススクリプト
# IAM認証付きでCloud Runサービスにアクセスするためのプロキシを起動

set -e

# 設定読み込み
if [ -f .env ]; then
    source .env
else
    echo "Error: .env ファイルが見つかりません"
    exit 1
fi

# 必須変数チェック
: "${REGION:?REGION が設定されていません}"
: "${SERVICE_NAME:?SERVICE_NAME が設定されていません}"

echo "=== Cloud Run Proxy 起動 ==="
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo ""
echo "ローカルプロキシを起動します..."
echo "ブラウザで http://localhost:8080 にアクセスしてください"
echo ""
echo "終了するには Ctrl+C を押してください"
echo ""

# Cloud Run Proxy を起動 (IAM認証を自動処理)
gcloud run services proxy "${SERVICE_NAME}" \
    --region "${REGION}" \
    --port 8080
