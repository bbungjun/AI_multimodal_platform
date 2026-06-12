resource "aws_ecs_task_definition" "dispatcher" {
  family                   = "${local.name_prefix}-dispatcher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.dispatcher_cpu)
  memory                   = tostring(var.dispatcher_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "dispatcher"
      image     = var.container_image
      essential = true
      command   = ["python", "-m", "app.services.jobs.outbox_dispatcher"]

      environment = concat(
        local.backend_common_environment,
        [
          { name = "OUTBOX_DISPATCHER_BATCH_SIZE", value = "50" },
          { name = "OUTBOX_DISPATCHER_POLL_INTERVAL_SEC", value = "1.0" },
          { name = "OUTBOX_DISPATCHER_MAX_ATTEMPTS", value = "10" }
        ]
      )
      secrets = local.database_url_secret

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.dispatcher.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "dispatcher"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "dispatcher" {
  name             = "${local.name_prefix}-dispatcher"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.dispatcher.arn
  desired_count    = var.dispatcher_desired_count
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  enable_execute_command = var.enable_ecs_execute_command

  network_configuration {
    subnets          = local.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = var.assign_public_ip
  }
}
