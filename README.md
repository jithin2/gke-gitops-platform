# gke-gitops-platform

![Terraform](https://img.shields.io/badge/Terraform-1.6+-623CE4?logo=terraform&logoColor=white)
![GKE](https://img.shields.io/badge/GKE-1.29+-4285F4?logo=googlecloud&logoColor=white)
![ArgoCD](https://img.shields.io/badge/ArgoCD-2.10+-EF7B4D?logo=argo&logoColor=white)
![Go](https://img.shields.io/badge/Go-1.22+-00ADD8?logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A production-grade Kubernetes platform on Google Cloud, built around GitOps principles with ArgoCD. The platform provisions a private GKE cluster via Terraform, deploys a multi-service application through Kustomize overlays across three environments, and enforces continuous delivery through a fully automated Git-driven workflow.

This repository demonstrates end-to-end ownership of cloud infrastructure, container orchestration, CI/CD, observability, and security hardening -- the kind of work a senior platform or cloud engineer delivers in production.

---

## Architecture Overview

```
                                  +---------------------+
                                  |   GitHub Actions CI  |
                                  |  build, push, tag   |
                                  +----------+----------+
                                             |
                                     image push to
                                  Artifact Registry
                                             |
  +----------+       +----------+            v            +-------------------+
  |          |       |  GCP     |   +--------+--------+   |                   |
  |  Users   +------>+  Cloud   +-->+   GKE Private    |   |  ArgoCD (in-      |
  |          |       |  Load    |   |   Cluster        |   |  cluster)         |
  +----------+       |  Balancer|   |                  |   |                   |
                     +----------+   |  +-----------+   |   |  watches git repo |
                                    |  | Frontend  |   |<--+  syncs manifests  |
                                    |  | (Go)      |   |   +-------------------+
                                    |  +-----+-----+   |
                                    |        |          |          +------------------+
                                    |        v          |          |  Terraform Cloud |
                                    |  +-----+-------+  |          |  / CLI           |
                                    |  | Order Svc   |  |<---------+  provisions:     |
                                    |  | (Python)    |  |          |  - VPC / subnets |
                                    |  +-----+-------+  |          |  - GKE cluster   |
                                    |        |          |          |  - IAM / WI      |
                                    |        v          |          |  - Cloud NAT     |
                                    |  +-----+-------+  |          +------------------+
                                    |  | Product Svc |  |
                                    |  | (Python)    |  |    +------------------------+
                                    |  +-------------+  |    | Prometheus + Grafana   |
                                    |                   |    | metrics, alerts,       |
                                    +-------------------+    | dashboards             |
                                                             +------------------------+
```

**Data flow:** External traffic enters through a GCP HTTP(S) Load Balancer, terminates TLS, and routes to the frontend service inside the private GKE cluster. The frontend delegates to the order and product services over the internal ClusterIP network. All inter-service communication is governed by Kubernetes NetworkPolicies.

**Delivery flow:** Engineers push code to GitHub. GitHub Actions builds container images, pushes them to Artifact Registry, and patches the image tag in the Kustomize overlays. ArgoCD detects the manifest drift and reconciles the cluster to match the desired state declared in Git.

**Infrastructure flow:** Terraform provisions and manages the full GCP foundation -- VPC with private subnets, Cloud NAT for egress, a private GKE cluster with Workload Identity, and all associated IAM bindings. State is stored remotely in a GCS backend.

---

## Tech Stack

| Layer              | Technology                          | Purpose                                          |
|--------------------|-------------------------------------|--------------------------------------------------|
| Cloud Provider     | Google Cloud Platform               | Managed Kubernetes, networking, IAM              |
| Infrastructure     | Terraform (~1.6+)                   | Declarative, versioned infrastructure            |
| Orchestration      | GKE (private cluster, 1.29+)       | Container runtime with auto-scaling              |
| Networking         | VPC, Cloud NAT, Private Google Access | Private cluster egress and API access          |
| Identity           | Workload Identity Federation        | Keyless pod-to-GCP authentication                |
| Service Mesh / LB  | GKE Ingress (GCP HTTP(S) LB)      | External traffic routing and TLS termination     |
| GitOps Engine      | ArgoCD 2.10+                        | Declarative, Git-driven continuous delivery      |
| Manifest Mgmt      | Kustomize                           | Environment-specific overlays without templating |
| CI                 | GitHub Actions                      | Image build, registry push, manifest patching    |
| Container Registry | Artifact Registry                   | Regional, vulnerability-scanned image storage    |
| Frontend Service   | Go 1.22+ (distroless image)        | Lightweight, statically compiled HTTP service    |
| Backend Services   | Python 3.12+ (FastAPI / Flask)     | Order and product REST APIs                      |
| Monitoring         | Prometheus + Grafana                | Metrics collection, dashboards, alerting         |
| Policy             | Kubernetes NetworkPolicy            | East-west traffic segmentation                   |

---

## Project Structure

```
gke-gitops-platform/
|
|-- terraform/                       # Infrastructure as Code
|   |-- main.tf                      # Provider config, GKE cluster, node pools
|   |-- vpc.tf                       # VPC, subnets, Cloud NAT, Cloud Router
|   |-- iam.tf                       # Service accounts, Workload Identity bindings
|   |-- variables.tf                 # Input variables
|   |-- outputs.tf                   # Cluster endpoint, CA cert, project outputs
|   |-- backend.tf                   # GCS remote state configuration
|   +-- terraform.tfvars.example     # Example variable values
|
|-- k8s/
|   |-- base/                        # Kustomize base (shared across all envs)
|   |   |-- kustomization.yaml
|   |   |-- frontend/
|   |   |   |-- deployment.yaml
|   |   |   |-- service.yaml
|   |   |   |-- hpa.yaml
|   |   |   |-- network-policy.yaml
|   |   |   +-- ingress.yaml
|   |   |-- order-service/
|   |   |   |-- deployment.yaml
|   |   |   |-- service.yaml
|   |   |   |-- hpa.yaml
|   |   |   +-- network-policy.yaml
|   |   +-- product-service/
|   |       |-- deployment.yaml
|   |       |-- service.yaml
|   |       |-- hpa.yaml
|   |       +-- network-policy.yaml
|   +-- overlays/
|       |-- dev/                      # Low resource limits, 1 replica
|       |   |-- kustomization.yaml
|       |   +-- patches/
|       |-- staging/                  # Mid-tier resources, 2 replicas, PDBs
|       |   |-- kustomization.yaml
|       |   +-- patches/
|       +-- prod/                     # Full resources, 3+ replicas, PDBs, anti-affinity
|           |-- kustomization.yaml
|           +-- patches/
|
|-- argocd/
|   |-- app-of-apps.yaml             # Root application that manages all child apps
|   |-- appproject.yaml              # AppProject with RBAC and source restrictions
|   |-- apps/
|   |   |-- dev.yaml                 # Application targeting k8s/overlays/dev
|   |   |-- staging.yaml             # Application targeting k8s/overlays/staging
|   |   +-- prod.yaml                # Application targeting k8s/overlays/prod
|   +-- argocd-cm-patch.yaml         # ArgoCD ConfigMap customizations
|
|-- services/
|   |-- frontend/                    # Go HTTP frontend
|   |   |-- main.go
|   |   |-- Dockerfile               # Multi-stage build, distroless final image
|   |   +-- go.mod
|   |-- order-service/               # Python order API
|   |   |-- app.py
|   |   |-- requirements.txt
|   |   +-- Dockerfile
|   +-- product-service/             # Python product API
|       |-- app.py
|       |-- requirements.txt
|       +-- Dockerfile
|
|-- .github/
|   +-- workflows/
|       +-- ci.yaml                  # Build images, push to AR, patch image tags
|
|-- monitoring/
|   |-- prometheus/
|   |   |-- prometheus-config.yaml   # Scrape configs, service discovery
|   |   +-- alert-rules.yaml         # Alerting rules (latency, error rate, saturation)
|   +-- grafana/
|       |-- datasources.yaml
|       +-- dashboards/
|           +-- platform-overview.json
|
+-- README.md
```

---

## Prerequisites

| Tool        | Minimum Version | Installation |
|-------------|-----------------|--------------|
| gcloud CLI  | 460+            | https://cloud.google.com/sdk/docs/install |
| Terraform   | 1.6+            | https://developer.hashicorp.com/terraform/install |
| kubectl     | 1.29+           | `gcloud components install kubectl` |
| Kustomize   | 5.0+            | https://kubectl.docs.kubernetes.io/installation/kustomize/ |
| ArgoCD CLI  | 2.10+           | https://argo-cd.readthedocs.io/en/stable/cli_installation/ |
| Docker      | 24+             | https://docs.docker.com/get-docker/ |
| Go          | 1.22+           | https://go.dev/dl/ (for local frontend development) |
| Python      | 3.12+           | https://www.python.org/downloads/ (for local backend development) |

You will also need:
- A GCP project with billing enabled.
- The following APIs enabled: `container.googleapis.com`, `compute.googleapis.com`, `artifactregistry.googleapis.com`, `iam.googleapis.com`.
- A GCS bucket for Terraform remote state (or create one during bootstrap).

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/<your-org>/gke-gitops-platform.git
cd gke-gitops-platform

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
```

### 2. Provision infrastructure with Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project ID, region, and cluster settings

terraform init
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

This creates:
- A custom VPC with private subnets and secondary ranges for pods/services.
- A Cloud Router and Cloud NAT for outbound internet access from private nodes.
- A private GKE cluster with Workload Identity enabled.
- Node pools configured with spot instances and auto-scaling.
- IAM service accounts bound via Workload Identity Federation.

### 3. Connect to the cluster

```bash
gcloud container clusters get-credentials gke-gitops-cluster \
  --region <YOUR_REGION> \
  --project <YOUR_PROJECT_ID>

# Verify connectivity
kubectl get nodes
```

### 4. Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for pods to become ready
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/part-of=argocd \
  -n argocd --timeout=180s
```

### 5. Deploy the app-of-apps

```bash
# Create the AppProject (defines RBAC and source/destination constraints)
kubectl apply -f argocd/appproject.yaml

# Deploy the root application (manages all environment apps)
kubectl apply -f argocd/app-of-apps.yaml
```

ArgoCD will now discover and deploy all child applications (dev, staging, prod) from their respective overlay directories.

### 6. Access ArgoCD UI

```bash
# Retrieve the initial admin password
argocd admin initial-password -n argocd

# Port-forward the ArgoCD server
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open https://localhost:8080 in your browser
# Username: admin
# Password: <output from above>
```

### 7. Deploy monitoring stack

```bash
kubectl create namespace monitoring
kubectl apply -f monitoring/prometheus/ -n monitoring
kubectl apply -f monitoring/grafana/ -n monitoring
```

---

## GitOps Workflow

This platform follows a strict GitOps model: **Git is the single source of truth for both infrastructure and application state.**

```
Developer pushes code
        |
        v
+-------+--------+
| GitHub Actions  |  1. Lint and test the code
|    CI Pipeline  |  2. Build container image
|                 |  3. Push to Artifact Registry
|                 |  4. Patch image tag in k8s/overlays/<env>/kustomization.yaml
+-------+--------+  5. Commit and push the manifest change
        |
        v
+-------+--------+
| Git Repository  |  Updated manifests now reflect the new image tag
+-------+--------+
        |
        v
+-------+--------+
| ArgoCD          |  Detects drift between Git (desired state) and
|                 |  cluster (live state) via periodic polling or webhook
+-------+--------+
        |
        v
+-------+--------+
| GKE Cluster     |  ArgoCD applies the updated manifests
|                 |  Kubernetes performs a rolling update
+----------------+
```

**Key properties:**
- **Declarative:** Every change is a Git commit. There are no imperative `kubectl apply` commands in the delivery path.
- **Auditable:** Git history provides a complete, immutable audit trail of who changed what and when.
- **Reversible:** Rolling back is a `git revert`. ArgoCD detects the reverted state and reconciles.
- **Environment promotion:** Changes flow through `dev` -> `staging` -> `prod` overlays via pull requests, with review gates at each stage.

---

## Key Design Decisions

### Kustomize over Helm

Helm introduces a templating layer that obscures the final rendered manifests. Kustomize operates on plain YAML through strategic merge patches, which means every environment's output is directly readable and diffable. For a platform with well-defined base manifests and small per-environment deltas (replica count, resource limits, PDB thresholds), Kustomize eliminates unnecessary abstraction. There is no template engine to debug, no values schema to maintain, and `kubectl kustomize` shows exactly what will be applied.

### App-of-Apps pattern

Managing each environment's ArgoCD Application as a separate resource quickly becomes error-prone at scale. The app-of-apps pattern consolidates all Application definitions under a single root Application. Adding a new environment or service means adding a YAML file to the `argocd/apps/` directory -- ArgoCD discovers it automatically. This also enables atomic updates: the root app's sync status reflects the health of the entire platform.

### Workload Identity over key-based service account auth

Exporting GCP service account keys creates long-lived credentials that must be rotated, stored securely, and monitored for leaks. Workload Identity Federation maps Kubernetes service accounts directly to GCP IAM identities through OIDC federation. Pods authenticate to GCP APIs without any keys. This eliminates an entire class of credential management risk and aligns with Google's recommended practice for GKE workloads.

### Private cluster with Cloud NAT

GKE nodes in this platform have no public IP addresses. The API server endpoint is also restricted. This reduces the attack surface to the absolute minimum for a managed Kubernetes cluster. Cloud NAT provides outbound internet access (for pulling images, reaching external APIs) without exposing any node to inbound public traffic.

### Spot (preemptible) node pools

Non-production workloads (and stateless production workloads with proper PDBs and anti-affinity) tolerate node preemption. Spot VMs reduce compute cost by 60-91% compared to on-demand instances. The platform mitigates preemption risk through Pod Disruption Budgets, topology spread constraints, and multiple replicas across zones.

### NetworkPolicies for east-west segmentation

By default, Kubernetes allows unrestricted pod-to-pod communication. This platform applies deny-all base policies and explicitly allows only the required traffic paths (frontend -> order-service, frontend -> product-service, order-service -> product-service). A compromised pod cannot pivot to arbitrary services within the cluster.

### Distroless container images

The Go frontend uses `gcr.io/distroless/static` as its final image. Distroless images contain no shell, no package manager, and no OS utilities. This minimizes the container's attack surface, reduces image size, and produces cleaner vulnerability scan results compared to `alpine` or `debian-slim` bases.

---

## Security Features

| Feature | Implementation | Risk Mitigated |
|---------|---------------|----------------|
| **Private GKE cluster** | Nodes have no public IPs; API server access is restricted | Unauthorized cluster access from the internet |
| **Workload Identity** | Pod-to-GCP auth via OIDC federation, no exported keys | Credential leakage, key rotation burden |
| **NetworkPolicies** | Deny-all default with explicit allow rules per service | Lateral movement after container compromise |
| **Distroless images** | No shell or OS packages in production containers | Container escape, RCE via system binaries |
| **Least-privilege IAM** | Each service account has only the permissions it needs | Privilege escalation, blast radius of compromise |
| **Private Artifact Registry** | Images stored regionally with vulnerability scanning | Supply chain attacks, malicious image injection |
| **RBAC on ArgoCD AppProject** | Source repos, destination clusters, and namespaces are constrained | Unauthorized deployments, cross-env drift |
| **Pod Security Standards** | Containers run as non-root with read-only root filesystems | Container privilege escalation |
| **Cloud NAT (no public egress IPs on nodes)** | All outbound traffic routes through NAT gateway | Direct exploitation of node network interfaces |

---

## Cost Optimization

| Strategy | Estimated Savings | Details |
|----------|-------------------|---------|
| **Spot / preemptible nodes** | 60-91% on compute | Stateless services tolerate preemption; PDBs ensure availability during node drain |
| **Cluster autoscaler** | Variable | Scales node pools to zero during off-hours in dev/staging; right-sizes prod based on actual demand |
| **Regional cluster (not multi-zonal)** | ~33% on control plane | Single-region deployment is sufficient for non-HA dev/staging environments |
| **HPA (Horizontal Pod Autoscaler)** | Variable | Scales pods based on CPU/memory utilization; avoids over-provisioning replicas at baseline |
| **E2 machine family** | 30% vs N2 | Cost-optimized VM family for workloads that do not require sustained high CPU |
| **Committed Use Discounts** | 37-55% | For predictable production baseline capacity (applied at the billing account level) |
| **Resource requests/limits tuning** | Variable | Per-environment overlays set right-sized CPU/memory to avoid bin-packing waste |
| **Cloud NAT (vs. static external IPs)** | Minor | Pay per usage rather than reserving static IPs that may sit idle |
| **Artifact Registry (vs. Container Registry)** | Minor | Regional storage reduces cross-region egress; lifecycle policies clean up old image tags |

**Dev/staging cost control:** The dev and staging overlays run minimal replica counts (1-2), reduced resource requests, and use spot-only node pools. The cluster autoscaler can scale dev node pools to zero outside of business hours using a scheduled scaling policy or a CronJob that cordons and drains nodes.

---

## Environment Comparison

| Property | Dev | Staging | Prod |
|----------|-----|---------|------|
| Replicas (per service) | 1 | 2 | 3+ |
| CPU request | 50m | 100m | 250m |
| Memory request | 64Mi | 128Mi | 256Mi |
| HPA enabled | No | Yes | Yes |
| PodDisruptionBudget | No | Yes (minAvailable: 1) | Yes (minAvailable: 2) |
| Anti-affinity | No | Preferred | Required |
| Node pool type | Spot | Spot | Spot + on-demand mix |
| NetworkPolicies | Enforced | Enforced | Enforced |

---

## Monitoring and Alerting

The `monitoring/` directory contains a Prometheus and Grafana stack configured for platform observability.

**Prometheus scrape targets:**
- Kubernetes API server metrics
- kubelet and cAdvisor container metrics
- Node Exporter system metrics
- ArgoCD application controller metrics
- Custom application metrics exposed on `/metrics` endpoints

**Alert rules include:**
- High error rate (5xx responses > 1% over 5 minutes)
- Elevated p99 latency (> 500ms over 5 minutes)
- Pod crash loop detection (restart count > 3 in 10 minutes)
- Node memory pressure (> 85% utilization)
- ArgoCD application out-of-sync for more than 10 minutes
- PVC usage approaching capacity (> 80%)

**Grafana dashboards:**
- Platform overview: cluster health, node utilization, pod counts by namespace
- Per-service dashboards: request rate, error rate, latency percentiles (RED method)
- ArgoCD dashboard: sync status, application health, reconciliation duration

---

## Local Development

```bash
# Run the frontend locally
cd services/frontend
go run main.go

# Run order-service locally
cd services/order-service
pip install -r requirements.txt
python app.py

# Run product-service locally
cd services/product-service
pip install -r requirements.txt
python app.py

# Preview Kustomize output for any environment
kubectl kustomize k8s/overlays/dev
kubectl kustomize k8s/overlays/prod
```

---

## Contributing

1. Create a feature branch from `main`.
2. Make changes and test locally.
3. Open a pull request targeting `main`.
4. CI runs lint, test, and build steps automatically.
5. After merge, ArgoCD detects the change and syncs the target environment.

---

## License

MIT
