# Cloud Workstations 変数定義

variable "project_id" {
  description = "GCPプロジェクトID"
  type        = string
}

variable "region" {
  description = "リージョン"
  type        = string
  default     = "asia-northeast1"
}

variable "network_name" {
  description = "VPCネットワーク名"
  type        = string
}

variable "subnet_name" {
  description = "サブネット名"
  type        = string
}

variable "cluster_name" {
  description = "Workstation Cluster名"
  type        = string
  default     = "workstation-cluster"
}

variable "config_name" {
  description = "Workstation Config名"
  type        = string
  default     = "workstation-config"
}

variable "workstation_name" {
  description = "Workstation名"
  type        = string
  default     = "dev-workstation"
}

variable "machine_type" {
  description = "マシンタイプ"
  type        = string
  default     = "e2-standard-4"
}

variable "boot_disk_size_gb" {
  description = "ブートディスクサイズ (GB)"
  type        = number
  default     = 35
}

variable "idle_timeout" {
  description = "アイドルタイムアウト (秒)"
  type        = string
  default     = "1800s"  # 30分
}

variable "running_timeout" {
  description = "最大稼働時間 (秒)"
  type        = string
  default     = "43200s"  # 12時間
}
