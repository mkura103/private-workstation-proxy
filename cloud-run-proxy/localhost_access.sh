#!/bin/bash
# Cloud Run Proxy Server アクセススクリプト
# IAM認証付きでCloud Runサービスにアクセスするためのプロキシを起動

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TFVARS_FILE="${SCRIPT_DIR}/terraform.tfvars"

# terraform.tfvars から値を取得する関数
get_tfvar() {
    local key=$1
    grep "^${key}" "${TFVARS_FILE}" | sed 's/.*=\s*"\([^"]*\)".*/\1/' | head -1
}

# 設定読み込み
if [ ! -f "${TFVARS_FILE}" ]; then
    echo "Error: terraform.tfvars が見つかりません"
    exit 1
fi

REGION=$(get_tfvar "region")
SERVICE_NAME=$(get_tfvar "service_name")

# デフォルト値
REGION="${REGION:-asia-northeast1}"
SERVICE_NAME="${SERVICE_NAME:-workstation-proxy}"

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
