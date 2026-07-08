resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.name_prefix}-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}
