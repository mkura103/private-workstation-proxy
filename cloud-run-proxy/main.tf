# Cloud Run Proxy Server - Terraform Configuration

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Data sources
data "google_project" "current" {
  project_id = var.project_id
}

data "google_compute_network" "main" {
  name    = var.network
  project = var.project_id
}

data "google_compute_subnetwork" "main" {
  name    = var.subnet
  region  = var.region
  project = var.project_id
}

# Artifact Registry Repository
resource "google_artifact_registry_repository" "cloud_run_source" {
  location      = var.region
  repository_id = "cloud-run-source-deploy"
  format        = "DOCKER"
  description   = "Docker repository for Cloud Run source deployments"
}

# Build and push container image using Cloud Build
resource "null_resource" "build_and_push" {
  triggers = {
    # Rebuild when these files change
    proxy_hash       = filemd5("${path.module}/proxy.py")
    dockerfile_hash  = filemd5("${path.module}/Dockerfile")
    requirements_hash = filemd5("${path.module}/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      gcloud builds submit \
        --project ${var.project_id} \
        --region ${var.region} \
        --tag ${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.cloud_run_source.repository_id}/${var.service_name}:latest \
        ${path.module}
    EOT
  }

  depends_on = [google_artifact_registry_repository.cloud_run_source]
}

# Cloud Run Service
resource "google_cloud_run_v2_service" "proxy" {
  name     = var.service_name
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.cloud_run_source.repository_id}/${var.service_name}:latest"

      env {
        name  = "CLUSTER_HOSTNAME"
        value = var.cluster_hostname
      }

      env {
        name  = "AUTH_MODE"
        value = var.auth_mode
      }

      dynamic "env" {
        for_each = var.auth_mode == "password" ? [1] : []
        content {
          name  = "PROXY_PASSWORD"
          value = var.proxy_password
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    timeout = "3600s"

    vpc_access {
      network_interfaces {
        network    = data.google_compute_network.main.id
        subnetwork = data.google_compute_subnetwork.main.id
      }
      egress = "ALL_TRAFFIC"
    }
  }

  depends_on = [null_resource.build_and_push]
}

# IAM: Allow public access when auth_mode is password
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count = var.auth_mode == "password" ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.proxy.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# IAM: Grant specific users access when auth_mode is iap
resource "google_cloud_run_v2_service_iam_member" "iap_users" {
  for_each = var.auth_mode == "iap" ? toset(var.iap_users) : toset([])

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.proxy.name
  role     = "roles/run.invoker"
  member   = each.value
}
