# Cloud Workstations 出力定義

output "cluster_id" {
  description = "Workstation Cluster ID"
  value       = google_workstations_workstation_cluster.main.workstation_cluster_id
}

output "workstation_id" {
  description = "Workstation ID"
  value       = google_workstations_workstation.main.workstation_id
}

output "cluster_hostname" {
  description = "Private Cluster ホスト名"
  value       = google_workstations_workstation_cluster.main.private_cluster_config[0].cluster_hostname
}

output "workstation_host" {
  description = "Workstation ホスト名 (Cloud Run Proxyの WORKSTATION_HOST に設定)"
  value       = "${google_workstations_workstation.main.workstation_id}.${google_workstations_workstation_cluster.main.private_cluster_config[0].cluster_hostname}"
}

output "psc_endpoint_ip" {
  description = "PSCエンドポイントの内部IPアドレス"
  value       = google_compute_address.psc_endpoint.address
}
