# Cloud Workstations Private Access via Cloud Run Proxy

Private設定のCloud Workstationsに、Cloud Runをプロキシサーバーとして経由してアクセスするための構成。

## アーキテクチャ

```
[ユーザーPC]
    ↓ gcloud run services proxy (IAP認証) または 直接アクセス (パスワード認証)
[Cloud Run Proxy (Python aiohttp)]
    ↓ Direct VPC Egress
[Private VPC (default)]
    ↓ PSC (Private Service Connect)
[Cloud Workstations (Private Endpoint)]
```

## 認証モード

| モード | 用途 | 認証方式 |
|--------|------|----------|
| `password` | 個人プロジェクト (組織なし) | プロキシ側でパスワード認証 |
| `iap` | 組織プロジェクト | Cloud Run IAM + IAP認証 |

## 認証フロー

```
1. Cloud Run → メタデータサーバー → GCPアクセストークン取得
2. Cloud Run → Workstation API (generateAccessToken) → Workstationアクセストークン取得
3. Cloud Run → Workstation (Authorization: Bearer TOKEN)
```

## フォルダ構成

```
.
├── README.md
├── workstations/                 # Cloud Workstations (Terraform)
│   ├── main.tf                   # Cluster, Config, Workstation, PSC, DNS, NAT
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tfvars          # 設定値 (gitignore対象)
│   └── terraform.tfvars.example
└── cloud-run-proxy/              # Cloud Run プロキシサーバー (Terraform + Python)
    ├── proxy.py                  # aiohttp WebSocket対応プロキシ
    ├── Dockerfile
    ├── requirements.txt
    ├── main.tf                   # Cloud Run, Artifact Registry
    ├── variables.tf
    ├── outputs.tf
    ├── terraform.tfvars          # 設定値 (gitignore対象)
    ├── terraform.tfvars.example
    ├── gethostname.sh            # cluster_hostname 取得・更新
    └── access.sh                 # ローカルプロキシ起動
```

## デプロイ手順

### Step 1: API有効化

```bash
gcloud services enable \
  workstations.googleapis.com \
  run.googleapis.com \
  compute.googleapis.com \
  cloudbuild.googleapis.com \
  dns.googleapis.com \
  artifactregistry.googleapis.com \
  --project=YOUR_PROJECT_ID
```

### Step 2: Cloud Workstations デプロイ

```bash
cd workstations
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集
terraform init
terraform apply
```

### Step 3: Cloud Run Proxy デプロイ

```bash
cd cloud-run-proxy
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

# cluster_hostname を自動取得
./gethostname.sh

terraform init
terraform apply
```

### Step 4: 接続

```bash
cd cloud-run-proxy
./access.sh
# ブラウザで http://localhost:8080/ws/{workstation-name}/ にアクセス
```

## 複数Workstation対応

パスベースルーティングで複数のWorkstationにアクセス可能:

```
/ws/alice/ → alice.cluster-xxx.cloudworkstations.dev
/ws/bob/   → bob.cluster-xxx.cloudworkstations.dev
```

## Workstation状態管理

`/status/{workstation-name}` でWorkstationの状態確認・開始/停止が可能:

```
http://localhost:8080/status/dev-workstation
```

| 機能 | 説明 |
|------|------|
| 状態表示 | STATE_RUNNING (緑), STATE_STOPPED (赤), STATE_STARTING/STOPPING (黄) |
| 開始ボタン | STATE_STOPPEDの時に表示 |
| 停止ボタン | STATE_RUNNINGの時に表示 |
| Open Workstationリンク | STATE_RUNNINGの時のみ表示 |

## 制約事項

- Cloud Runの最大タイムアウトは60分
- 60分を超える接続は自動再接続が必要
- WebSocket対応済み（VS Code IDE完全動作）

## ライセンス

MIT
