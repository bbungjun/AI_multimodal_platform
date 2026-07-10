variable "project_name" {
  type    = string
  default = "creativeops"
}

variable "environment" {
  type    = string
  default = "portfolio"
}

variable "gcp_project_id" {
  type        = string
  description = "Google Cloud project id where the portfolio stack is deployed."
}

variable "gcp_region" {
  type    = string
  default = "asia-northeast3"
}

variable "gcp_zone" {
  type    = string
  default = "asia-northeast3-a"
}

variable "network_cidr" {
  type    = string
  default = "10.50.0.0/20"
}

variable "pods_cidr" {
  type    = string
  default = "10.52.0.0/16"
}

variable "services_cidr" {
  type    = string
  default = "10.53.0.0/20"
}

variable "node_machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "node_count" {
  type    = number
  default = 1
}

variable "node_pool_autoscaling_enabled" {
  type        = bool
  default     = false
  description = "Enable GKE node pool autoscaling. Keep disabled unless a cost-aware autoscaling issue is actively validating it."
}

variable "node_pool_autoscaling_min_count" {
  type        = number
  default     = 0
  description = "Minimum node count when node pool autoscaling is enabled."
}

variable "node_pool_autoscaling_max_count" {
  type        = number
  default     = 2
  description = "Maximum node count when node pool autoscaling is enabled."
}

variable "backend_image" {
  type        = string
  description = "Full Artifact Registry backend image URI including tag."
}

variable "frontend_image" {
  type        = string
  description = "Full Artifact Registry frontend image URI including tag."
}

variable "api_replicas" {
  type    = number
  default = 0
}

variable "frontend_replicas" {
  type    = number
  default = 0
}

variable "api_hpa_enabled" {
  type        = bool
  default     = false
  description = "Enable a HorizontalPodAutoscaler for the API deployment. Keep disabled unless explicitly validating workload autoscaling."
}

variable "api_hpa_min_replicas" {
  type        = number
  default     = 2
  description = "Minimum API replicas when api_hpa_enabled is true."
}

variable "api_hpa_max_replicas" {
  type        = number
  default     = 4
  description = "Maximum API replicas when api_hpa_enabled is true."
}

variable "api_hpa_cpu_target_utilization" {
  type        = number
  default     = 70
  description = "Average CPU utilization percentage target for the API HPA."

  validation {
    condition     = var.api_hpa_cpu_target_utilization >= 1 && var.api_hpa_cpu_target_utilization <= 100
    error_message = "api_hpa_cpu_target_utilization must be between 1 and 100."
  }
}

variable "frontend_hpa_enabled" {
  type        = bool
  default     = false
  description = "Enable a HorizontalPodAutoscaler for the frontend deployment. Keep disabled unless explicitly validating workload autoscaling."
}

variable "frontend_hpa_min_replicas" {
  type        = number
  default     = 2
  description = "Minimum frontend replicas when frontend_hpa_enabled is true."
}

variable "frontend_hpa_max_replicas" {
  type        = number
  default     = 4
  description = "Maximum frontend replicas when frontend_hpa_enabled is true."
}

variable "frontend_hpa_cpu_target_utilization" {
  type        = number
  default     = 70
  description = "Average CPU utilization percentage target for the frontend HPA."

  validation {
    condition     = var.frontend_hpa_cpu_target_utilization >= 1 && var.frontend_hpa_cpu_target_utilization <= 100
    error_message = "frontend_hpa_cpu_target_utilization must be between 1 and 100."
  }
}

variable "worker_replicas" {
  type    = number
  default = 0
}

variable "dispatcher_replicas" {
  type    = number
  default = 0
}

variable "ai_provider" {
  type    = string
  default = "mock"

  validation {
    condition     = contains(["mock", "vertex"], var.ai_provider)
    error_message = "ai_provider must be mock or vertex."
  }
}

variable "vertex_location" {
  type    = string
  default = "us-central1"
}

variable "enhance_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "db_name" {
  type    = string
  default = "multimodal"
}

variable "db_username" {
  type    = string
  default = "app"
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "db_edition" {
  type    = string
  default = "ENTERPRISE"

  validation {
    condition     = contains(["ENTERPRISE", "ENTERPRISE_PLUS"], var.db_edition)
    error_message = "db_edition must be ENTERPRISE or ENTERPRISE_PLUS."
  }
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "redis_memory_size_gb" {
  type    = number
  default = 1
}

variable "rate_limit_gemini_per_min" {
  type    = number
  default = 10
}

variable "rate_limit_imagen_per_min" {
  type    = number
  default = 5
}

variable "rate_limit_veo_per_min" {
  type    = number
  default = 1
}

variable "celery_worker_concurrency" {
  type    = number
  default = 2
}

variable "monitoring_alerts_enabled" {
  type        = bool
  default     = false
  description = "Create Cloud Monitoring alert policies for CreativeOps Prometheus metrics. Enable only after metric ingestion is verified."
}

variable "monitoring_notification_channel_names" {
  type        = list(string)
  default     = []
  description = "Existing Cloud Monitoring notification channel resource names attached to CreativeOps alert policies."
}

variable "monitoring_http_5xx_error_rate_threshold" {
  type        = number
  default     = 0.05
  description = "HTTP 5xx error-rate threshold over a five-minute PromQL window."

  validation {
    condition = (
      var.monitoring_http_5xx_error_rate_threshold > 0 &&
      var.monitoring_http_5xx_error_rate_threshold <= 1
    )
    error_message = "monitoring_http_5xx_error_rate_threshold must be greater than 0 and no greater than 1."
  }
}

variable "monitoring_http_min_requests_per_window" {
  type        = number
  default     = 20
  description = "Minimum requests in the five-minute window before the HTTP 5xx alert can fire."

  validation {
    condition     = var.monitoring_http_min_requests_per_window >= 1
    error_message = "monitoring_http_min_requests_per_window must be at least 1."
  }
}

variable "monitoring_provider_failures_per_window" {
  type        = number
  default     = 3
  description = "Provider failures with the same code in five minutes required to fire an alert."

  validation {
    condition     = var.monitoring_provider_failures_per_window >= 1
    error_message = "monitoring_provider_failures_per_window must be at least 1."
  }
}

variable "monitoring_dashboard_slo_enabled" {
  type        = bool
  default     = false
  description = "Create the CreativeOps reliability dashboard, custom service, and availability SLO after Prometheus ingestion is verified."
}

variable "monitoring_availability_slo_goal" {
  type        = number
  default     = 0.995
  description = "Fraction of eligible API requests that must avoid HTTP 5xx responses during the rolling SLO period."

  validation {
    condition = (
      var.monitoring_availability_slo_goal > 0 &&
      var.monitoring_availability_slo_goal <= 0.999
    )
    error_message = "monitoring_availability_slo_goal must be greater than 0 and no greater than 0.999."
  }
}

variable "monitoring_availability_slo_rolling_days" {
  type        = number
  default     = 28
  description = "Rolling evaluation period in days for the API availability SLO."

  validation {
    condition = (
      var.monitoring_availability_slo_rolling_days >= 1 &&
      var.monitoring_availability_slo_rolling_days <= 30
    )
    error_message = "monitoring_availability_slo_rolling_days must be between 1 and 30."
  }
}
