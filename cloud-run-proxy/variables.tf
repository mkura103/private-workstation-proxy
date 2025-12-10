variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-northeast1"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "workstation-proxy"
}

variable "network" {
  description = "VPC network name"
  type        = string
  default     = "default"
}

variable "subnet" {
  description = "Subnet name"
  type        = string
  default     = "default"
}

variable "cluster_hostname" {
  description = "Workstation cluster hostname (e.g., cluster-xxx.cloudworkstations.dev)"
  type        = string
}

variable "iap_users" {
  description = "List of users/groups to grant Cloud Run invoker role. Format: 'user:email@example.com' or 'group:group@example.com'"
  type        = list(string)
  default     = []
}
