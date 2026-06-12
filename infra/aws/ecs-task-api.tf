resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.api_cpu)
  memory                   = tostring(var.api_memory)
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
      name      = "api"
      image     = var.container_image
      essential = true
      command   = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = local.backend_common_environment
      secrets     = local.backend_common_secrets

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
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name             = "${local.name_prefix}-api"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.api.arn
  desired_count    = var.api_desired_count
  launch_type      = "FARGATE"
  platform_version = "1.4.0"

  enable_execute_command = var.enable_ecs_execute_command

  network_configuration {
    subnets          = local.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = var.assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.http,
    aws_efs_mount_target.assets
  ]
}
