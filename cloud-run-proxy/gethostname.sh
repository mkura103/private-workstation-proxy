#!/bin/bash
# Workstations Terraform から cluster_hostname を取得して terraform.tfvars を更新

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSTATIONS_DIR="${SCRIPT_DIR}/../workstations"
TFVARS_FILE="${SCRIPT_DIR}/terraform.tfvars"

# Workstations ディレクトリの存在確認
if [ ! -d "${WORKSTATIONS_DIR}" ]; then
    echo "Error: workstations ディレクトリが見つかりません: ${WORKSTATIONS_DIR}"
    exit 1
fi

# terraform.tfstate の存在確認
if [ ! -f "${WORKSTATIONS_DIR}/terraform.tfstate" ]; then
    echo "Error: terraform.tfstate が見つかりません"
    echo "先に workstations で terraform apply を実行してください"
    exit 1
fi

# cluster_hostname を取得
CLUSTER_HOSTNAME=$(terraform -chdir="${WORKSTATIONS_DIR}" output -raw cluster_hostname 2>/dev/null)

if [ -z "${CLUSTER_HOSTNAME}" ]; then
    echo "Error: cluster_hostname を取得できませんでした"
    exit 1
fi

echo "取得した cluster_hostname: ${CLUSTER_HOSTNAME}"

# terraform.tfvars を更新
if [ -f "${TFVARS_FILE}" ]; then
    # 既存の cluster_hostname 行を置換
    sed -i '' "s|^cluster_hostname.*|cluster_hostname = \"${CLUSTER_HOSTNAME}\"|" "${TFVARS_FILE}"
    echo "terraform.tfvars を更新しました"
else
    echo "Error: terraform.tfvars が見つかりません: ${TFVARS_FILE}"
    exit 1
fi

echo ""
echo "cluster_hostname = \"${CLUSTER_HOSTNAME}\""
