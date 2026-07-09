resource "kubernetes_horizontal_pod_autoscaler_v2" "api" {
  count = var.api_hpa_enabled ? 1 : 0

  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-api"
    }
  }

  spec {
    min_replicas = var.api_hpa_min_replicas
    max_replicas = var.api_hpa_max_replicas

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.api.metadata[0].name
    }

    metric {
      type = "Resource"

      resource {
        name = "cpu"

        target {
          type                = "Utilization"
          average_utilization = var.api_hpa_cpu_target_utilization
        }
      }
    }

    behavior {
      scale_up {
        stabilization_window_seconds = 60
        select_policy                = "Max"

        policy {
          type           = "Pods"
          value          = 2
          period_seconds = 60
        }

        policy {
          type           = "Percent"
          value          = 100
          period_seconds = 60
        }
      }

      scale_down {
        stabilization_window_seconds = 300
        select_policy                = "Max"

        policy {
          type           = "Pods"
          value          = 1
          period_seconds = 60
        }

        policy {
          type           = "Percent"
          value          = 50
          period_seconds = 60
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.api_hpa_min_replicas <= var.api_hpa_max_replicas
      error_message = "api_hpa_min_replicas must be less than or equal to api_hpa_max_replicas."
    }

    precondition {
      condition     = var.api_replicas == var.api_hpa_min_replicas
      error_message = "When api_hpa_enabled is true, set api_replicas equal to api_hpa_min_replicas so Terraform's initial desired replica count matches the HPA floor."
    }
  }
}

resource "kubernetes_horizontal_pod_autoscaler_v2" "frontend" {
  count = var.frontend_hpa_enabled ? 1 : 0

  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-frontend"
    }
  }

  spec {
    min_replicas = var.frontend_hpa_min_replicas
    max_replicas = var.frontend_hpa_max_replicas

    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment_v1.frontend.metadata[0].name
    }

    metric {
      type = "Resource"

      resource {
        name = "cpu"

        target {
          type                = "Utilization"
          average_utilization = var.frontend_hpa_cpu_target_utilization
        }
      }
    }

    behavior {
      scale_up {
        stabilization_window_seconds = 60
        select_policy                = "Max"

        policy {
          type           = "Pods"
          value          = 2
          period_seconds = 60
        }

        policy {
          type           = "Percent"
          value          = 100
          period_seconds = 60
        }
      }

      scale_down {
        stabilization_window_seconds = 300
        select_policy                = "Max"

        policy {
          type           = "Pods"
          value          = 1
          period_seconds = 60
        }

        policy {
          type           = "Percent"
          value          = 50
          period_seconds = 60
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.frontend_hpa_min_replicas <= var.frontend_hpa_max_replicas
      error_message = "frontend_hpa_min_replicas must be less than or equal to frontend_hpa_max_replicas."
    }

    precondition {
      condition     = var.frontend_replicas == var.frontend_hpa_min_replicas
      error_message = "When frontend_hpa_enabled is true, set frontend_replicas equal to frontend_hpa_min_replicas so Terraform's initial desired replica count matches the HPA floor."
    }
  }
}
