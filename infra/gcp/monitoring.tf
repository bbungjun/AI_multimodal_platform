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

locals {
  monitoring_application_path_matcher = "/metrics|/api/health|/api/health/live|unmatched"
  monitoring_request_metric_filter = join(" AND ", [
    "metric.type=\"prometheus.googleapis.com/creativeops_http_requests_total/counter\"",
    "resource.type=\"prometheus_target\"",
    "resource.label.\"namespace\"=\"${local.namespace}\"",
    "metric.label.\"path\"!=\"/metrics\"",
    "metric.label.\"path\"!=\"/api/health\"",
    "metric.label.\"path\"!=\"/api/health/live\"",
    "metric.label.\"path\"!=\"unmatched\"",
  ])
}

resource "google_monitoring_custom_service" "api" {
  count = var.monitoring_dashboard_slo_enabled ? 1 : 0

  service_id   = "creativeops-api"
  display_name = "CreativeOps API"

  user_labels = local.labels

  depends_on = [google_project_service.required]
}

resource "google_monitoring_slo" "api_availability" {
  count = var.monitoring_dashboard_slo_enabled ? 1 : 0

  service             = google_monitoring_custom_service.api[0].service_id
  slo_id              = "availability-28d"
  display_name        = "CreativeOps API availability"
  goal                = var.monitoring_availability_slo_goal
  rolling_period_days = var.monitoring_availability_slo_rolling_days

  request_based_sli {
    good_total_ratio {
      bad_service_filter = join(" AND ", [
        local.monitoring_request_metric_filter,
        "metric.label.\"status\"=starts_with(\"5\")",
      ])
      total_service_filter = local.monitoring_request_metric_filter
    }
  }

  user_labels = local.labels

  depends_on = [kubernetes_manifest.api_pod_monitoring]
}

resource "google_monitoring_dashboard" "reliability" {
  count = var.monitoring_dashboard_slo_enabled ? 1 : 0

  dashboard_json = jsonencode({
    displayName = "CreativeOps API Reliability"
    labels      = local.labels
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Request throughput"
          xyChart = {
            dataSets = [{
              legendTemplate = "requests/s"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                prometheusQuery = "sum(rate(creativeops_http_requests_total{namespace=\"${local.namespace}\", path!~\"${local.monitoring_application_path_matcher}\"}[5m]))"
                unitOverride    = "1/s"
              }
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "HTTP 5xx ratio"
          xyChart = {
            dataSets = [{
              legendTemplate = "5xx ratio"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                prometheusQuery = "sum(rate(creativeops_http_requests_total{namespace=\"${local.namespace}\", path!~\"${local.monitoring_application_path_matcher}\", status=~\"5..\"}[5m])) / clamp_min(sum(rate(creativeops_http_requests_total{namespace=\"${local.namespace}\", path!~\"${local.monitoring_application_path_matcher}\"}[5m])), 0.000001)"
                unitOverride    = "10^2.%"
              }
            }]
            thresholds = [{
              value     = var.monitoring_http_5xx_error_rate_threshold
              direction = "ABOVE"
              color     = "RED"
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "HTTP request latency p95"
          xyChart = {
            dataSets = [{
              legendTemplate = "p95"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                prometheusQuery = "histogram_quantile(0.95, sum by (le) (rate(creativeops_http_request_duration_milliseconds_bucket{namespace=\"${local.namespace}\", path!~\"${local.monitoring_application_path_matcher}\"}[5m])))"
                unitOverride    = "ms"
              }
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "Prompt provider failures by code"
          xyChart = {
            dataSets = [{
              legendTemplate = "$${code}"
              plotType       = "STACKED_BAR"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                prometheusQuery = "sum by (code) (increase(creativeops_provider_failures_total{namespace=\"${local.namespace}\"}[5m]))"
                unitOverride    = "1"
              }
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "Availability SLO compliance"
          xyChart = {
            dataSets = [{
              legendTemplate = "good / total"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "select_slo_compliance(\"${google_monitoring_slo.api_availability[0].name}\")"
                  aggregation = {
                    perSeriesAligner = "ALIGN_NEXT_OLDER"
                  }
                }
                unitOverride = "10^2.%"
              }
            }]
            thresholds = [{
              value     = var.monitoring_availability_slo_goal
              direction = "BELOW"
              color     = "RED"
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "Availability error budget remaining"
          xyChart = {
            dataSets = [{
              legendTemplate = "remaining bad requests"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "select_slo_budget(\"${google_monitoring_slo.api_availability[0].name}\")"
                  aggregation = {
                    perSeriesAligner = "ALIGN_NEXT_OLDER"
                  }
                }
                unitOverride = "1"
              }
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
        {
          title = "Availability error-budget burn rate (1h)"
          xyChart = {
            dataSets = [{
              legendTemplate = "burn rate"
              plotType       = "LINE"
              targetAxis     = "Y1"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "select_slo_burn_rate(\"${google_monitoring_slo.api_availability[0].name}\", \"3600s\")"
                  aggregation = {
                    perSeriesAligner = "ALIGN_NEXT_OLDER"
                  }
                }
                unitOverride = "1"
              }
            }]
            thresholds = [{
              value     = 1
              direction = "ABOVE"
              color     = "RED"
            }]
            yAxis = { scale = "LINEAR" }
          }
        },
      ]
    }
  })

  depends_on = [google_monitoring_slo.api_availability]
}
