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

variable "auth_mode" {
  description = "Authentication mode: 'password' or 'iap'"
  type        = string
  default     = "password"
}

variable "proxy_password" {
  description = "Password for proxy authentication (required when auth_mode is 'password')"
  type        = string
  sensitive   = true
  default     = "changeme"
}

variable "iap_users" {
  description = "List of users/groups to grant Cloud Run invoker role (required when auth_mode is 'iap'). Format: 'user:email@example.com' or 'group:group@example.com'"
  type        = list(string)
  default     = []
}
