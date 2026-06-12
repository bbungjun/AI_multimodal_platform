resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_cpu)
  memory                   = tostring(var.worker_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "assets"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.assets.id
      transit_encryption = "ENABLED"

      authorization_config {
        access_point_id = aws_efs_access_point.assets.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.container_image
      essential = true
      command = [
        "celery",
        "-A",
        "app.celery_app",
        "worker",
        "--loglevel=info",
        "--queues=generation",
        "--concurrency=${var.celery_worker_concurrency}"
      ]

      environment = concat(
        local.backend_common_environment,
        [
          { name = "CELERY_WORKER_CONCURRENCY", value = tostring(var.celery_worker_concurrency) },
          { name = "CELERY_WORKER_SHUTDOWN_GRACE_SEC", value = "60" },
          { name = "CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC", value = "5" }
        ]
      )
      secrets = local.backend_common_secrets

      mountPoints = [
        {
          sourceVolume  = "assets"
          containerPath = "/data/assets"
          readOnly      = false
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name             = "${local.name_prefix}-worker"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.worker.arn
  desired_count    = var.worker_desired_count
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  enable_execute_command = var.enable_ecs_execute_command

  network_configuration {
    subnets          = local.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = var.assign_public_ip
  }

  depends_on = [aws_efs_mount_target.assets]
}
