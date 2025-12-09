# Cloud Workstations 最小構成
# - Cluster (コントロールプレーン) × 1
# - Config × 1
# - Workstation × 1

terraform {
  required_version = ">= 1.0"
  required_providers {
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# データソース: 既存のVPCネットワーク
data "google_compute_network" "main" {
  provider = google-beta
  name     = var.network_name
}

# データソース: 既存のサブネット
data "google_compute_subnetwork" "main" {
  provider = google-beta
  name     = var.subnet_name
  region   = var.region
}

# Workstation Cluster (コントロールプレーン)
resource "google_workstations_workstation_cluster" "main" {
  provider               = google-beta
  workstation_cluster_id = var.cluster_name
  location               = var.region

  network    = data.google_compute_network.main.id
  subnetwork = data.google_compute_subnetwork.main.id

  # Private Cluster設定
  private_cluster_config {
    enable_private_endpoint = true
  }

  labels = {
    environment = "development"
  }
}

# Workstation Config
resource "google_workstations_workstation_config" "main" {
  provider               = google-beta
  workstation_config_id  = var.config_name
  workstation_cluster_id = google_workstations_workstation_cluster.main.workstation_cluster_id
  location               = var.region

  # マシン設定
  host {
    gce_instance {
      machine_type      = var.machine_type
      boot_disk_size_gb = var.boot_disk_size_gb

      # 外部IPなし (Private)
      disable_public_ip_addresses = true
    }
  }

  # タイムアウト設定
  idle_timeout    = var.idle_timeout
  running_timeout = var.running_timeout

  # 永続ホームディレクトリ
  persistent_directories {
    mount_path = "/home"
    gce_pd {
      size_gb        = 200
      fs_type        = "ext4"
      reclaim_policy = "DELETE"
    }
  }
}

# Workstation インスタンス
resource "google_workstations_workstation" "main" {
  provider               = google-beta
  workstation_id         = var.workstation_name
  workstation_config_id  = google_workstations_workstation_config.main.workstation_config_id
  workstation_cluster_id = google_workstations_workstation_cluster.main.workstation_cluster_id
  location               = var.region

  labels = {
    environment = "development"
  }
}

# Cloud RunサービスアカウントにWorkstation Userロールを付与
resource "google_workstations_workstation_iam_member" "cloud_run_user" {
  provider               = google-beta
  project                = var.project_id
  location               = var.region
  workstation_cluster_id = google_workstations_workstation_cluster.main.workstation_cluster_id
  workstation_config_id  = google_workstations_workstation_config.main.workstation_config_id
  workstation_id         = google_workstations_workstation.main.workstation_id
  role                   = "roles/workstations.user"
  member                 = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

# プロジェクト番号取得用
data "google_project" "current" {
  project_id = var.project_id
}

# =============================================================================
# Private Service Connect (PSC) 設定
# Private Clusterへの接続に必要
# =============================================================================

# PSCエンドポイント用の内部IPアドレス
resource "google_compute_address" "psc_endpoint" {
  name         = "workstation-psc-endpoint"
  address_type = "INTERNAL"
  subnetwork   = data.google_compute_subnetwork.main.id
  region       = var.region
}

# PSCフォワーディングルール
resource "google_compute_forwarding_rule" "psc_endpoint" {
  name                  = "workstation-psc-forwarding-rule"
  region                = var.region
  network               = data.google_compute_network.main.id
  ip_address            = google_compute_address.psc_endpoint.id
  load_balancing_scheme = ""
  target                = google_workstations_workstation_cluster.main.private_cluster_config[0].service_attachment_uri
}

# プライベートDNSゾーン (cloudworkstations.dev)
resource "google_dns_managed_zone" "workstations" {
  name        = "workstations-private-zone"
  dns_name    = "cloudworkstations.dev."
  description = "Private DNS zone for Cloud Workstations"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = data.google_compute_network.main.id
    }
  }
}

# DNSレコード (クラスターホスト名 → PSCエンドポイント)
resource "google_dns_record_set" "workstation_cluster" {
  managed_zone = google_dns_managed_zone.workstations.name
  name         = "${google_workstations_workstation_cluster.main.private_cluster_config[0].cluster_hostname}."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_address.psc_endpoint.address]
}

# DNSレコード (ワイルドカード: *.cluster-xxx → PSCエンドポイント)
# Workstationホスト名 (dev-workstation.cluster-xxx...) の解決に必要
resource "google_dns_record_set" "workstation_wildcard" {
  managed_zone = google_dns_managed_zone.workstations.name
  name         = "*.${google_workstations_workstation_cluster.main.private_cluster_config[0].cluster_hostname}."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_address.psc_endpoint.address]
}

# =============================================================================
# Cloud NAT 設定
# Private Workstation VMがコンテナイメージをプルするために必要
# =============================================================================

# Cloud Router
resource "google_compute_router" "main" {
  name    = "workstation-router"
  network = data.google_compute_network.main.id
  region  = var.region
}

# Cloud NAT (対象サブネットのみ)
resource "google_compute_router_nat" "main" {
  name                               = "workstation-nat"
  router                             = google_compute_router.main.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = data.google_compute_subnetwork.main.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = false
    filter = "ALL"
  }
}
