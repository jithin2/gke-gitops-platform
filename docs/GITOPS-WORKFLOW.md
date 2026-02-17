# GitOps Workflow Deep-Dive

## What is GitOps?

GitOps is an operational framework where **Git is the single source of truth** for declarative infrastructure and application configuration. Changes are made via pull requests, and an operator (ArgoCD) ensures the live state matches the desired state in Git.

### Core Principles
1. **Declarative** — The entire system is described declaratively (YAML manifests)
2. **Versioned and Immutable** — Git stores the canonical desired state with full history
3. **Pulled Automatically** — Approved changes are automatically applied to the system
4. **Continuously Reconciled** — Software agents ensure the actual state matches desired state

---

## Our GitOps Pipeline

```
Developer → Git Push → GitHub Actions (CI) → Build Image → Push to Artifact Registry
                                                    ↓
                                            Update image tag in k8s/overlays/
                                                    ↓
                                            Git Commit (automated)
                                                    ↓
                                            ArgoCD detects change
                                                    ↓
                                            ArgoCD syncs to GKE cluster
                                                    ↓
                                            Kubernetes rolls out new pods
```

### Step-by-Step Flow

#### 1. Developer Pushes Code
```bash
git checkout -b feature/add-caching
# Make changes to services/order-service/main.py
git add .
git commit -m "feat: add Redis caching layer"
git push origin feature/add-caching
```

#### 2. Pull Request + CI
- PR triggers GitHub Actions CI pipeline
- Pipeline validates K8s manifests (`kustomize build`)
- Pipeline builds Docker image
- Pipeline runs tests
- After merge to `main`:
  - Image pushed to Artifact Registry with git SHA tag
  - CI updates image tag in `k8s/overlays/dev/kustomization.yaml`
  - CI commits the tag update back to the repo

#### 3. ArgoCD Detects Change
ArgoCD polls the Git repo (default: every 3 minutes) or receives a webhook:
```
ArgoCD detects: k8s/overlays/dev/kustomization.yaml changed
  → Image tag updated from abc1234 to def5678
  → Application status: OutOfSync
```

#### 4. ArgoCD Syncs (Dev: Automated)
For dev environment, auto-sync is enabled:
```yaml
syncPolicy:
  automated:
    prune: true      # Remove resources deleted from Git
    selfHeal: true   # Revert manual changes
```

ArgoCD applies the manifests:
```
kubectl apply -k k8s/overlays/dev/
```

#### 5. Kubernetes Rolling Update
```
Deployment "order-service" updated
  → New ReplicaSet created with image: order-service:def5678
  → Old pods terminated gradually (maxUnavailable: 0, maxSurge: 1)
  → Readiness probes pass → traffic shifted
  → Old ReplicaSet scaled to 0
```

---

## Environment Promotion Strategy

```
main branch
├── k8s/overlays/dev/        ← Auto-sync (every commit)
├── k8s/overlays/staging/    ← Auto-sync (after dev validation)
└── k8s/overlays/prod/       ← Manual sync (requires approval)
```

### Promoting to Staging
```bash
# After dev is validated, update staging image tag
cd k8s/overlays/staging
kustomize edit set image \
  .../order-service=.../order-service:def5678

git add .
git commit -m "promote: order-service def5678 to staging"
git push
# ArgoCD auto-syncs staging
```

### Promoting to Production
```bash
# Update prod with a release tag
cd k8s/overlays/prod
kustomize edit set image \
  .../order-service=.../order-service:v1.2.0

git add .
git commit -m "release: order-service v1.2.0 to production"
git push
# ArgoCD shows OutOfSync — requires manual sync button click
```

**Why manual sync for prod?**
- Gives operators a final gate before production changes
- Allows scheduling deployments during maintenance windows
- ArgoCD UI shows exactly what will change (diff view)

---

## Rollback Strategies

### Strategy 1: Git Revert (Preferred)
```bash
# Revert the commit that promoted the bad version
git revert HEAD
git push
# ArgoCD syncs back to the previous image tag
```

**Why preferred?** Full audit trail in Git. The revert is a new commit, not history rewrite.

### Strategy 2: ArgoCD History Rollback
```bash
# List sync history
argocd app history frontend-prod

# Rollback to a previous sync
argocd app rollback frontend-prod <REVISION>
```

**Caveat:** This creates drift between Git and cluster state. ArgoCD will show OutOfSync. You should still update Git to match.

### Strategy 3: Kustomize Image Override
```bash
cd k8s/overlays/prod
kustomize edit set image \
  .../order-service=.../order-service:v1.1.0  # Previous known-good version

git commit -am "rollback: order-service to v1.1.0"
git push
```

---

## Kustomize Structure Explained

### Why Kustomize over Helm?

| Aspect | Kustomize | Helm |
|--------|-----------|------|
| Templating | Patches (overlay) | Go templates |
| Readability | Plain YAML | Template syntax |
| GitOps fit | Native — files are valid K8s YAML | Requires render step |
| Learning curve | Lower | Higher |
| Flexibility | Strategic merge patches | Full templating power |

For this project, Kustomize was chosen because:
1. Manifests are valid YAML at every layer (base + overlays)
2. Easier to review in PRs (no template variables to resolve mentally)
3. ArgoCD has native Kustomize support
4. Simpler mental model for environment promotion

### Base + Overlay Pattern

```
k8s/
├── base/                    # Shared across all environments
│   ├── frontend/
│   │   ├── deployment.yaml  # 2 replicas, 100m/128Mi resources
│   │   ├── service.yaml
│   │   └── hpa.yaml
│   ├── network-policies/
│   └── kustomization.yaml
├── overlays/
│   ├── dev/                 # 1 replica, 50m/64Mi, auto-sync
│   │   ├── kustomization.yaml
│   │   └── patches/
│   ├── staging/             # 2 replicas, base resources, auto-sync
│   └── prod/                # 3 replicas, 250m/256Mi, PDB, anti-affinity, manual sync
│       ├── kustomization.yaml
│       ├── pdb.yaml         # Extra resource only in prod
│       └── patches/
│           ├── replicas.yaml
│           ├── resources.yaml
│           └── anti-affinity.yaml
```

---

## App-of-Apps Pattern

The app-of-apps pattern uses a **root ArgoCD Application** that manages child Applications:

```
argocd/
├── app-of-apps.yaml          # Root Application → watches argocd/applications/
├── applications/
│   └── frontend.yaml         # Contains dev, staging, prod Application resources
└── projects/
    └── platform.yaml         # AppProject with RBAC
```

### Benefits
1. **Single entry point** — Deploy one Application, get everything
2. **Self-managing** — Adding a new service = adding a YAML file
3. **RBAC isolation** — AppProject restricts which namespaces/resources each team can deploy
4. **Bootstrapping** — `kubectl apply -f argocd/app-of-apps.yaml` sets up the entire platform

---

## Secret Management in GitOps

Secrets cannot be stored in Git in plaintext. Options:

### Option 1: External Secrets Operator (Recommended)
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-credentials
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: gcp-secret-manager
    kind: ClusterSecretStore
  target:
    name: db-credentials
  data:
    - secretKey: password
      remoteRef:
        key: projects/PROJECT_ID/secrets/db-password/versions/latest
```

**Why?** Secrets stay in GCP Secret Manager. Only references are in Git.

### Option 2: Sealed Secrets
```bash
# Encrypt secret with cluster's public key
kubeseal --format yaml < secret.yaml > sealed-secret.yaml
# sealed-secret.yaml is safe to commit to Git
```

### Option 3: SOPS (Mozilla)
```bash
# Encrypt specific values in YAML
sops --encrypt --gcp-kms projects/PROJECT_ID/locations/global/keyRings/sops/cryptoKeys/sops-key secret.yaml
```

This project uses **External Secrets Operator + GCP Secret Manager** because:
- Secrets are centrally managed in GCP
- Automatic rotation via Secret Manager versioning
- Workload Identity provides secure access (no key files)
- Clean separation: Git has the "what", Secret Manager has the "value"

---

## Monitoring GitOps Health

### ArgoCD Metrics
ArgoCD exposes Prometheus metrics at `/metrics`:
- `argocd_app_info` — Application sync status
- `argocd_app_sync_total` — Sync operations count
- `argocd_app_reconcile_duration_seconds` — Reconciliation latency

### Key Alerts
```yaml
# Alert if any app is OutOfSync for too long
- alert: ArgoCDAppOutOfSync
  expr: argocd_app_info{sync_status="OutOfSync"} == 1
  for: 30m
  annotations:
    summary: "ArgoCD app {{ $labels.name }} has been OutOfSync for 30m"
```

### ArgoCD CLI Monitoring
```bash
# Check all application statuses
argocd app list

# Watch sync status in real-time
argocd app get frontend-prod --refresh

# View sync history
argocd app history frontend-prod
```
