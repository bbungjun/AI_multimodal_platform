resource "kubernetes_namespace_v1" "app" {
  metadata {
    name = local.namespace
    labels = {
      app = "creativeops"
    }
  }

  depends_on = [google_container_node_pool.general]
}

resource "kubernetes_service_account_v1" "app" {
  metadata {
    name      = local.app_service_account
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.app.email
    }
  }
}
