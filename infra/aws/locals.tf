data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  public_subnet_count  = min(length(var.public_subnet_cidrs), 2)
  private_subnet_count = min(length(var.private_subnet_cidrs), 2)

  ecs_subnet_ids = var.assign_public_ip ? aws_subnet.public[*].id : aws_subnet.private[*].id

  backend_common_environment = [
    { name = "AI_PROVIDER", value = var.ai_provider },
    { name = "DATA_DIR", value = "/data/assets" },
    { name = "JOB_RUNNER_AUTO_START", value = "false" },
    { name = "JOB_DISPATCH_MODE", value = "celery" },
    { name = "CELERY_BROKER_URL", value = "redis://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0" },
    { name = "CELERY_DEFAULT_QUEUE", value = "generation" },
    { name = "RATE_LIMIT_GEMINI_PER_MIN", value = tostring(var.rate_limit_gemini_per_min) },
    { name = "RATE_LIMIT_IMAGEN_PER_MIN", value = tostring(var.rate_limit_imagen_per_min) },
    { name = "RATE_LIMIT_VEO_PER_MIN", value = tostring(var.rate_limit_veo_per_min) },
    { name = "PROVIDER_RETRY_MAX_ATTEMPTS", value = "3" },
    { name = "PROVIDER_RETRY_BASE_DELAY_SEC", value = "1.0" },
    { name = "PROVIDER_RETRY_MAX_DELAY_SEC", value = "20.0" },
    { name = "CELERY_TASK_ACKS_LATE", value = "true" },
    { name = "CELERY_TASK_REJECT_ON_WORKER_LOST", value = "true" },
    { name = "CELERY_WORKER_PREFETCH_MULTIPLIER", value = "1" },
    { name = "GCP_PROJECT_ID", value = var.gcp_project_id },
    { name = "GCP_LOCATION", value = var.gcp_location },
    { name = "ENHANCE_MODEL", value = var.enhance_model },
    { name = "CORS_ORIGINS", value = jsonencode(var.cors_origins) }
  ]

  database_url_secret = [
    {
      name      = "DATABASE_URL"
      valueFrom = aws_secretsmanager_secret.database_url.arn
    }
  ]

  vertex_credentials_secret = [
    {
      name      = "GOOGLE_APPLICATION_CREDENTIALS_JSON"
      valueFrom = aws_secretsmanager_secret.gcp_credentials_json.arn
    }
  ]

  backend_common_secrets = concat(
    local.database_url_secret,
    var.ai_provider == "vertex" ? local.vertex_credentials_secret : []
  )
}
