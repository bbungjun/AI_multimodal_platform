resource "google_artifact_registry_repository" "backend" {
  location      = var.gcp_region
  repository_id = local.backend_repository_id
  description   = "CreativeOps backend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_artifact_registry_repository" "frontend" {
  location      = var.gcp_region
  repository_id = local.frontend_repository_id
  description   = "CreativeOps frontend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}
