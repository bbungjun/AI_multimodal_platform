output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  value = var.aws_region
}

output "backend_ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.app.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.app.id
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "database_url_secret_arn" {
  value = aws_secretsmanager_secret.database_url.arn
}

output "gcp_credentials_json_secret_arn" {
  value = aws_secretsmanager_secret.gcp_credentials_json.arn
}

output "rds_endpoint" {
  value = aws_db_instance.main.address
}

output "rds_master_secret_arn" {
  value = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "efs_file_system_id" {
  value = aws_efs_file_system.assets.id
}
