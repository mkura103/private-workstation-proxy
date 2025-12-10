# Cloud Workstations (Terraform)

Private設定のCloud Workstationsを最小構成でデプロイするTerraform構成。

## リソース構成

| リソース | 数 | 説明 |
|----------|:--:|------|
| Workstation Cluster | 1 | コントロールプレーン (Private Endpoint) |
| Workstation Config | 1 | マシン設定 |
| Workstation | 1 | 開発環境インスタンス |
| PSC Endpoint | 1 | Private Service Connect |
| DNS Zone | 1 | cloudworkstations.dev プライベートゾーン |
| DNS Records | 2 | クラスター + ワイルドカード |
| Cloud NAT | 1 | コンテナイメージプル用 |
| IAM Binding | 1 | Cloud Runサービスアカウント用 |

## ファイル構成

| ファイル | 説明 |
|----------|------|
| `main.tf` | リソース定義 |
| `variables.tf` | 変数定義 |
| `outputs.tf` | 出力定義 |
| `terraform.tfvars` | 設定値 (gitignore対象) |
| `terraform.tfvars.example` | 設定テンプレート |

## 使用方法

```bash
# 初期化
terraform init

# 確認
terraform plan

# デプロイ (約15分)
terraform apply

# 削除
terraform destroy
```

## 出力値

| 出力 | 説明 |
|------|------|
| `cluster_id` | クラスターID |
| `cluster_hostname` | クラスターホスト名 (cloud-run-proxy で使用) |
| `workstation_id` | ワークステーションID |
| `workstation_host` | Cloud Run Proxyに設定するホスト名 |
| `psc_endpoint_ip` | PSCエンドポイントのIPアドレス |

## Terraform変数

| 変数 | 説明 | デフォルト |
|------|------|------------|
| `project_id` | GCPプロジェクトID | (必須) |
| `region` | リージョン | asia-northeast1 |
| `network_name` | VPCネットワーク名 | default |
| `subnet_name` | サブネット名 | default |
| `cluster_name` | クラスター名 | workstation-cluster |
| `config_name` | 設定名 | workstation-config |
| `workstation_name` | ワークステーション名 | dev-workstation |
| `machine_type` | マシンタイプ | e2-medium |
| `boot_disk_size_gb` | ブートディスクサイズ | 30 |
| `idle_timeout` | アイドルタイムアウト | 1800s (30分) |
| `running_timeout` | 最大実行時間 | 43200s (12時間) |

## Private Cluster設定

```hcl
private_cluster_config {
  enable_private_endpoint = true
}
```

この設定により、Workstationsはパブリックエンドポイントを持たず、VPC内からのみアクセス可能。

## PSC (Private Service Connect)

Private Clusterへの接続に必要なPSCエンドポイントを自動作成:

```hcl
resource "google_compute_forwarding_rule" "psc_endpoint" {
  target = google_workstations_workstation_cluster.main.private_cluster_config[0].service_attachment_uri
}
```

## DNS設定

プライベートDNSゾーンで名前解決:

| レコード | 値 |
|----------|-----|
| `cluster-xxx.cloudworkstations.dev` | PSC IP |
| `*.cluster-xxx.cloudworkstations.dev` | PSC IP (ワイルドカード) |

ワイルドカードレコードにより、`dev-workstation.cluster-xxx.cloudworkstations.dev` が解決可能。

## IAM Binding

Cloud RunサービスアカウントにWorkstation Userロールを付与:

```hcl
resource "google_workstations_workstation_iam_member" "cloud_run_user" {
  role   = "roles/workstations.user"
  member = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
```

これにより、Cloud RunからWorkstation APIの`generateAccessToken`が呼び出し可能。

## デプロイ時間

| リソース | 所要時間 |
|----------|----------|
| Workstation Cluster | 約14-15分 |
| Workstation Config | 約1分 |
| Workstation | 約10秒 |
| その他リソース | 約1分 |
| **合計** | **約16-17分** |

## Cloud NAT

Private Workstationsがコンテナイメージをプルするために必要:

```hcl
resource "google_compute_router_nat" "main" {
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
}
```
