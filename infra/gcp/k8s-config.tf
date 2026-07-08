resource "kubernetes_config_map_v1" "backend_env" {
  metadata {
    name      = "creativeops-backend-env"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  data = local.runtime_defaults
}

resource "kubernetes_persistent_volume_v1" "assets" {
  metadata {
    name = "${local.name_prefix}-assets"
  }

  spec {
    capacity = {
      storage = "1Ti"
    }
    access_modes                     = ["ReadWriteMany"]
    persistent_volume_reclaim_policy = "Retain"
    storage_class_name               = ""

    persistent_volume_source {
      csi {
        driver        = "gcsfuse.csi.storage.gke.io"
        volume_handle = google_storage_bucket.assets.name
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim_v1" "assets" {
  wait_until_bound = false

  metadata {
    name      = "creativeops-assets"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    access_modes       = ["ReadWriteMany"]
    storage_class_name = ""
    volume_name        = kubernetes_persistent_volume_v1.assets.metadata[0].name

    resources {
      requests = {
        storage = "1Ti"
      }
    }
  }
}
