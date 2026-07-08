locals {
  name_prefix = "${var.project_name}-${var.environment}"
  namespace   = local.name_prefix

  labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }

  backend_repository_id  = "${local.name_prefix}-backend"
  frontend_repository_id = "${local.name_prefix}-frontend"
  assets_bucket_name     = "${local.name_prefix}-assets-${var.gcp_project_id}"

  runtime_defaults = {
    AI_PROVIDER                       = var.ai_provider
    DATA_DIR                          = "/data/assets"
    JOB_RUNNER_AUTO_START             = "false"
    JOB_DISPATCH_MODE                 = "celery"
    CELERY_DEFAULT_QUEUE              = "generation"
    RATE_LIMIT_GEMINI_PER_MIN         = tostring(var.rate_limit_gemini_per_min)
    RATE_LIMIT_IMAGEN_PER_MIN         = tostring(var.rate_limit_imagen_per_min)
    RATE_LIMIT_VEO_PER_MIN            = tostring(var.rate_limit_veo_per_min)
    PROVIDER_RETRY_MAX_ATTEMPTS       = "3"
    PROVIDER_RETRY_BASE_DELAY_SEC     = "1.0"
    PROVIDER_RETRY_MAX_DELAY_SEC      = "20.0"
    CELERY_TASK_ACKS_LATE             = "true"
    CELERY_TASK_REJECT_ON_WORKER_LOST = "true"
    CELERY_WORKER_PREFETCH_MULTIPLIER = "1"
    CELERY_WORKER_CONCURRENCY         = tostring(var.celery_worker_concurrency)
    GCP_PROJECT_ID                    = var.gcp_project_id
    GCP_LOCATION                      = var.vertex_location
    ENHANCE_MODEL                     = var.enhance_model
    CORS_ORIGINS                      = "[]"
  }
}
