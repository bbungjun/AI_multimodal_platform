resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.project_name}/${var.environment}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/${var.project_name}/${var.environment}/worker"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "dispatcher" {
  name              = "/${var.project_name}/${var.environment}/dispatcher"
  retention_in_days = var.log_retention_days
}
