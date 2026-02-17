# -----------------------------------------------------------------------------
# GKE Service Account (least-privilege for nodes)
# -----------------------------------------------------------------------------
resource "google_service_account" "gke_nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "GKE Node Service Account"
  project      = var.project_id
}

# Minimal roles for GKE nodes
resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# -----------------------------------------------------------------------------
# Workload Identity — App Service Accounts
# Each K8s ServiceAccount maps to a GCP ServiceAccount
# -----------------------------------------------------------------------------

# Order Service — needs access to Cloud SQL, Pub/Sub
resource "google_service_account" "order_service" {
  account_id   = "order-service"
  display_name = "Order Service Workload Identity"
  project      = var.project_id
}

resource "google_project_iam_member" "order_service_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.order_service.email}"
}

resource "google_service_account_iam_binding" "order_service_wi" {
  service_account_id = google_service_account.order_service.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "serviceAccount:${var.project_id}.svc.id.goog[default/order-service]",
  ]
}

# Product Service — needs access to Cloud Storage
resource "google_service_account" "product_service" {
  account_id   = "product-service"
  display_name = "Product Service Workload Identity"
  project      = var.project_id
}

resource "google_project_iam_member" "product_service_gcs" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.product_service.email}"
}

resource "google_service_account_iam_binding" "product_service_wi" {
  service_account_id = google_service_account.product_service.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "serviceAccount:${var.project_id}.svc.id.goog[default/product-service]",
  ]
}

# -----------------------------------------------------------------------------
# Artifact Registry — Container image storage
# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "${var.cluster_name}-images"
  description   = "Container images for GitOps platform"
  format        = "DOCKER"
  project       = var.project_id

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
    }
  }
}
