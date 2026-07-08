resource "google_redis_instance" "main" {
  name           = "${local.name_prefix}-redis"
  tier           = "BASIC"
  memory_size_gb = var.redis_memory_size_gb
  region         = var.gcp_region

  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  depends_on = [google_service_networking_connection.private_services]
}
