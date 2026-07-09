resource "google_container_cluster" "main" {
  name     = local.name_prefix
  location = var.gcp_zone

  network    = google_compute_network.main.id
  subnetwork = google_compute_subnetwork.gke.id

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  addons_config {
    gcs_fuse_csi_driver_config {
      enabled = true
    }
  }

  release_channel {
    channel = "REGULAR"
  }

  depends_on = [
    google_project_service.required,
    google_compute_subnetwork.gke
  ]
}

resource "google_container_node_pool" "general" {
  name     = "${local.name_prefix}-general"
  cluster  = google_container_cluster.main.name
  location = google_container_cluster.main.location

  node_count = var.node_count

  lifecycle {
    precondition {
      condition = (
        var.node_count >= 2 ||
        (var.api_replicas <= 1 && var.frontend_replicas <= 1)
      )
      error_message = "Set node_count >= 2 when api_replicas or frontend_replicas is greater than 1. Readiness-gated RollingUpdate uses maxUnavailable=0 and maxSurge=1, so a single e2-standard-2 node can leave replacement pods Pending with Insufficient cpu."
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = var.node_machine_type
    service_account = google_service_account.gke_node.email

    labels = {
      workload = "creativeops-general"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  depends_on = [
    google_project_iam_member.node_artifact_reader,
    google_project_iam_member.node_log_writer,
    google_project_iam_member.node_metric_writer
  ]
}
