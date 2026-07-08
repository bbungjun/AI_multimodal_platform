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
