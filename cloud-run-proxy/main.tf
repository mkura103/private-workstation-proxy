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
        name  = "PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "REGION"
        value = var.region
      }

      env {
        name  = "CLUSTER_HOSTNAME"
        value = var.cluster_hostname
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
      egress = "PRIVATE_RANGES_ONLY"
    }
  }

  depends_on = [null_resource.build_and_push]
}

# IAM: Grant specific users access (Cloud Run invoker)
resource "google_cloud_run_v2_service_iam_member" "iap_users" {
  for_each = toset(var.iap_users)

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.proxy.name
  role     = "roles/run.invoker"
  member   = each.value
}

# Enable IAP on Cloud Run (via gcloud - not natively supported in Terraform)
# Triggers on every service update to ensure IAP stays enabled
resource "null_resource" "enable_iap" {
  triggers = {
    service_name     = google_cloud_run_v2_service.proxy.name
    service_revision = google_cloud_run_v2_service.proxy.latest_ready_revision
  }

  provisioner "local-exec" {
    command = <<-EOT
      gcloud beta run services update ${var.service_name} \
        --region=${var.region} \
        --project=${var.project_id} \
        --iap
    EOT
  }

  depends_on = [google_cloud_run_v2_service.proxy]
}

# Grant IAP access to users (via gcloud)
resource "null_resource" "iap_access" {
  for_each = toset(var.iap_users)

  triggers = {
    service_name = google_cloud_run_v2_service.proxy.name
    member       = each.value
  }

  provisioner "local-exec" {
    command = <<-EOT
      gcloud beta iap web add-iam-policy-binding \
        --region=${var.region} \
        --resource-type=cloud-run \
        --service=${var.service_name} \
        --project=${var.project_id} \
        --member="${each.value}" \
        --role="roles/iap.httpsResourceAccessor"
    EOT
  }

  depends_on = [null_resource.enable_iap]
}
