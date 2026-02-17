terraform {
  backend "gcs" {
    bucket = "myproject-terraform-state"
    prefix = "gke-gitops-platform"
  }
}
