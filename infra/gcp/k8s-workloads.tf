locals {
  app_secret_name = "creativeops-runtime-secrets"
}

resource "kubernetes_deployment_v1" "api" {
  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-api"
    }
  }

  spec {
    replicas                  = var.api_replicas
    min_ready_seconds         = 5
    progress_deadline_seconds = 180

    strategy {
      type = "RollingUpdate"

      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    selector {
      match_labels = {
        app = "creativeops-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-api"
        }
        annotations = {
          "creativeops.io/runtime-config-hash" = local.runtime_defaults_hash
          "gke-gcsfuse/volumes"                = "true"
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        volume {
          name = "assets"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.assets.metadata[0].name
          }
        }

        container {
          name    = "api"
          image   = var.backend_image
          command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

          port {
            container_port = 8000
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          volume_mount {
            name       = "assets"
            mount_path = "/data/assets"
          }

          readiness_probe {
            http_get {
              path = "/api/health"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          liveness_probe {
            http_get {
              path = "/api/health/live"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 20
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    selector = {
      app = "creativeops-api"
    }

    port {
      port        = 8000
      target_port = 8000
    }
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "kubernetes_pod_disruption_budget_v1" "api" {
  count = var.api_replicas > 1 ? 1 : 0

  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    min_available = 1

    selector {
      match_labels = {
        app = "creativeops-api"
      }
    }
  }
}

resource "kubernetes_deployment_v1" "worker" {
  metadata {
    name      = "creativeops-worker"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-worker"
    }
  }

  spec {
    replicas = var.worker_replicas

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = {
        app = "creativeops-worker"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-worker"
        }
        annotations = {
          "creativeops.io/runtime-config-hash" = local.runtime_defaults_hash
          "gke-gcsfuse/volumes"                = "true"
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        volume {
          name = "assets"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.assets.metadata[0].name
          }
        }

        container {
          name    = "worker"
          image   = var.backend_image
          command = ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--queues=generation", "--concurrency=${var.celery_worker_concurrency}"]

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name  = "CELERY_WORKER_CONCURRENCY"
            value = tostring(var.celery_worker_concurrency)
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          volume_mount {
            name       = "assets"
            mount_path = "/data/assets"
          }

          resources {
            requests = {
              cpu    = "200m"
              memory = "1Gi"
            }
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment_v1" "dispatcher" {
  metadata {
    name      = "creativeops-dispatcher"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-dispatcher"
    }
  }

  spec {
    replicas = var.dispatcher_replicas

    selector {
      match_labels = {
        app = "creativeops-dispatcher"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-dispatcher"
        }
        annotations = {
          "creativeops.io/runtime-config-hash" = local.runtime_defaults_hash
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        container {
          name    = "dispatcher"
          image   = var.backend_image
          command = ["python", "-m", "app.services.jobs.outbox_dispatcher"]

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          env {
            name  = "OUTBOX_DISPATCHER_BATCH_SIZE"
            value = "50"
          }

          env {
            name  = "OUTBOX_DISPATCHER_POLL_INTERVAL_SEC"
            value = "1.0"
          }

          env {
            name  = "OUTBOX_DISPATCHER_MAX_ATTEMPTS"
            value = "10"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment_v1" "frontend" {
  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-frontend"
    }
  }

  spec {
    replicas                  = var.frontend_replicas
    min_ready_seconds         = 5
    progress_deadline_seconds = 180

    strategy {
      type = "RollingUpdate"

      rolling_update {
        max_surge       = "1"
        max_unavailable = "0"
      }
    }

    selector {
      match_labels = {
        app = "creativeops-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-frontend"
        }
      }

      spec {
        container {
          name  = "frontend"
          image = var.frontend_image

          port {
            container_port = 8080
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 8080
            }
            initial_delay_seconds = 5
            period_seconds        = 10
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 8080
            }
            initial_delay_seconds = 30
            period_seconds        = 20
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "256Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "frontend" {
  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "creativeops-frontend"
    }

    port {
      port        = 80
      target_port = 8080
    }
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "kubernetes_pod_disruption_budget_v1" "frontend" {
  count = var.frontend_replicas > 1 ? 1 : 0

  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    min_available = 1

    selector {
      match_labels = {
        app = "creativeops-frontend"
      }
    }
  }
}
