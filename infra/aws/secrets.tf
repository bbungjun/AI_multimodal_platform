resource "aws_secretsmanager_secret" "database_url" {
  name        = "${local.name_prefix}/database-url"
  description = "Full SQLAlchemy DATABASE_URL for API, worker, and dispatcher tasks."
}

resource "aws_secretsmanager_secret" "gcp_credentials_json" {
  name        = "${local.name_prefix}/gcp-credentials-json"
  description = "Reserved for future Vertex credential JSON. Do not store this value in Terraform state."
}
