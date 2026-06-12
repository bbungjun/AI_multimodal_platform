variable "project_name" {
  type    = string
  default = "creativeops"
}

variable "environment" {
  type    = string
  default = "portfolio"
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-2"
}

variable "container_image" {
  type        = string
  description = "Full ECR image URI, including tag."
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.42.0.0/24", "10.42.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.42.10.0/24", "10.42.11.0/24"]
}

variable "allowed_http_cidr_blocks" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "use_nat_gateway" {
  type    = bool
  default = false
}

variable "assign_public_ip" {
  type        = bool
  default     = true
  description = "Set true for the low-cost first pass. Set false when private subnets have NAT or VPC endpoints."
}

variable "api_desired_count" {
  type    = number
  default = 0
}

variable "worker_desired_count" {
  type    = number
  default = 0
}

variable "dispatcher_desired_count" {
  type    = number
  default = 0
}

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "worker_cpu" {
  type    = number
  default = 1024
}

variable "worker_memory" {
  type    = number
  default = 2048
}

variable "dispatcher_cpu" {
  type    = number
  default = 256
}

variable "dispatcher_memory" {
  type    = number
  default = 512
}

variable "enable_ecs_execute_command" {
  type    = bool
  default = false
}

variable "ai_provider" {
  type    = string
  default = "mock"
}

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_location" {
  type    = string
  default = "us-central1"
}

variable "enhance_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "cors_origins" {
  type    = list(string)
  default = []
}

variable "db_name" {
  type    = string
  default = "multimodal"
}

variable "db_username" {
  type    = string
  default = "app"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_max_allocated_storage" {
  type    = number
  default = 100
}

variable "db_engine_version" {
  type    = string
  default = "16"
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_engine_version" {
  type    = string
  default = "7.1"
}

variable "redis_transit_encryption_enabled" {
  type    = bool
  default = false
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "frontend_price_class" {
  type    = string
  default = "PriceClass_100"
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
