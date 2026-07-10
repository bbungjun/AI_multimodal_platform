resource "kubernetes_manifest" "api_pod_monitoring" {
  manifest = {
    apiVersion = "monitoring.googleapis.com/v1"
    kind       = "PodMonitoring"
    metadata = {
      name      = "creativeops-api"
      namespace = kubernetes_namespace_v1.app.metadata[0].name
    }
    spec = {
      selector = {
        matchLabels = {
          app = "creativeops-api"
        }
      }
      endpoints = [
        {
          port     = "metrics"
          path     = "/metrics"
          interval = "30s"
          timeout  = "10s"
        }
      ]
    }
  }

  depends_on = [
    google_container_cluster.main,
    kubernetes_deployment_v1.api,
  ]
}

resource "google_monitoring_alert_policy" "api_http_5xx_error_rate" {
  count = var.monitoring_alerts_enabled ? 1 : 0

  display_name = "CreativeOps API HTTP 5xx error rate"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "API 5xx ratio exceeds threshold with meaningful traffic"

    condition_prometheus_query_language {
      query               = <<-EOT
        (
          sum(increase(creativeops_http_requests_total{namespace="${local.namespace}", path!~"/metrics|/api/health|/api/health/live|unmatched", status=~"5.."}[5m]))
          /
          clamp_min(sum(increase(creativeops_http_requests_total{namespace="${local.namespace}", path!~"/metrics|/api/health|/api/health/live|unmatched"}[5m])), 1)
        ) > ${var.monitoring_http_5xx_error_rate_threshold}
        and
        sum(increase(creativeops_http_requests_total{namespace="${local.namespace}", path!~"/metrics|/api/health|/api/health/live|unmatched"}[5m])) >= ${var.monitoring_http_min_requests_per_window}
      EOT
      duration            = "120s"
      evaluation_interval = "60s"
      rule_group          = "creativeops-api-reliability"
      alert_rule          = "CreativeOpsApiHigh5xxRate"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Check API rollout status, /api/health, and /api/ops/metrics. Compare recent image/config changes and roll back if the error rate remains elevated."
  }

  notification_channels = var.monitoring_notification_channel_names

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [
    google_project_service.required,
    kubernetes_manifest.api_pod_monitoring,
  ]
}

resource "google_monitoring_alert_policy" "provider_failures" {
  count = var.monitoring_alerts_enabled ? 1 : 0

  display_name = "CreativeOps prompt provider failures"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Provider failure code repeats within five minutes"

    condition_prometheus_query_language {
      query               = <<-EOT
        sum by (code) (
          increase(creativeops_provider_failures_total{namespace="${local.namespace}"}[5m])
        ) >= ${var.monitoring_provider_failures_per_window}
      EOT
      duration            = "60s"
      evaluation_interval = "60s"
      rule_group          = "creativeops-provider-reliability"
      alert_rule          = "CreativeOpsProviderFailures"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Inspect provider failure metrics by code, status, and retryability. Confirm rate-limit, timeout, or invalid-response behavior before retrying live traffic."
  }

  notification_channels = var.monitoring_notification_channel_names

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [
    google_project_service.required,
    kubernetes_manifest.api_pod_monitoring,
  ]
}
