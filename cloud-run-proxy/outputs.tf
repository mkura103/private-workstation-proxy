# Cloud Run Proxy Server - Outputs

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.proxy.uri
}

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.proxy.name
}

output "image_uri" {
  description = "Container image URI"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.cloud_run_source.repository_id}/${var.service_name}:latest"
}
