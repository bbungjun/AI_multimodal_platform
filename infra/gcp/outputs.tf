output "backend_repository_url" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.backend.repository_id}"
}

output "frontend_repository_url" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.frontend.repository_id}"
}

output "cluster_get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.main.name} --zone ${var.gcp_zone} --project ${var.gcp_project_id}"
}

output "cluster_name" {
  value = google_container_cluster.main.name
}

output "cluster_location" {
  value = google_container_cluster.main.location
}

output "workload_identity_pool" {
  value = google_container_cluster.main.workload_identity_config[0].workload_pool
}

output "app_google_service_account_email" {
  value = google_service_account.app.email
}

output "app_kubernetes_service_account_name" {
  value = local.app_service_account
}

output "namespace" {
  value = kubernetes_namespace_v1.app.metadata[0].name
}

output "monitoring_dashboard_name" {
  value = try(google_monitoring_dashboard.reliability[0].id, null)
}

output "monitoring_service_name" {
  value = try(google_monitoring_custom_service.api[0].name, null)
}

output "monitoring_availability_slo_name" {
  value = try(google_monitoring_slo.api_availability[0].name, null)
}

output "frontend_service_name" {
  value = kubernetes_service_v1.frontend.metadata[0].name
}

output "cloud_sql_instance_name" {
  value = google_sql_database_instance.main.name
}

output "cloud_sql_private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "database_name" {
  value = google_sql_database.app.name
}

output "redis_instance_name" {
  value = google_redis_instance.main.name
}

output "assets_bucket_name" {
  value = google_storage_bucket.assets.name
}
