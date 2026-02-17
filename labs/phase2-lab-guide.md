# Phase 2 Lab: ArgoCD & GitOps on Minikube

In Phase 1, you deployed manually with `helm install`. In Phase 2, you'll never run `helm install` or `kubectl apply` again. ArgoCD watches your Git repo and deploys automatically. **Git becomes the single source of truth.**

---

## Prerequisites

- Phase 1 completed (images built in Minikube)
- A free GitHub account
- `git` CLI installed

---

## Step 1: Push Your Repo to GitHub

**WHY:** ArgoCD needs a Git repo to watch. It polls the repo for changes and syncs the cluster to match. No Git repo = no GitOps.

```powershell
# 1. Create a new repo on GitHub (public, free)
#    Go to https://github.com/new
#    Name: gke-gitops-platform
#    Visibility: Public
#    Do NOT add README, .gitignore, or license (repo already has files)

# 2. Initialize git and push (run from the project root)
cd c:\Learning\Cloud_engineer

git init
git add .
git commit -m "Initial commit: full platform with Helm chart"

# 3. Connect to your GitHub repo (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/gke-gitops-platform.git
git branch -M main
git push -u origin main
```

**Verify:** Open your repo on GitHub. You should see all files — services, helm chart, k8s manifests, argocd configs.

---

## Step 2: Update the ArgoCD Application with Your Repo URL

**WHY:** The ArgoCD Application manifest tells ArgoCD WHERE to find your manifests. You need to replace the placeholder URL with your actual GitHub repo.

Edit `argocd/applications/minikube-helm.yaml`:

```yaml
  source:
    repoURL: https://github.com/YOUR_USERNAME/gke-gitops-platform.git  # <-- change this
```

Then commit and push:

```powershell
git add argocd/applications/minikube-helm.yaml
git commit -m "Update ArgoCD app with actual repo URL"
git push
```

---

## Step 3: Install ArgoCD in Minikube

**WHY:** ArgoCD is a Kubernetes controller that runs INSIDE your cluster. It watches Git repos and reconciles the cluster state to match what's in Git. Think of it as an automated operator that runs `helm upgrade` for you every time you push.

```powershell
# Create the argocd namespace
kubectl create namespace argocd

# Install ArgoCD (official manifests)
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for all ArgoCD pods to be ready (this may take 1-2 minutes)
kubectl wait --for=condition=Ready pod --all -n argocd --timeout=300s

# Verify ArgoCD is running
kubectl get pods -n argocd
```

You should see pods like:
- `argocd-server-xxx` — the API/UI server
- `argocd-repo-server-xxx` — clones and renders Git repos
- `argocd-application-controller-xxx` — the brain that syncs
- `argocd-redis-xxx` — cache
- `argocd-dex-server-xxx` — authentication

---

## Step 4: Access the ArgoCD UI

**WHY:** The UI is where you'll visually see the sync status, application health, and resource tree. Interviewers often ask "how do you monitor ArgoCD deployments?"

```powershell
# Get the initial admin password (auto-generated during install)
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }

# Copy that password! Username is: admin

# Port-forward the ArgoCD UI to your laptop
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open in browser: https://localhost:8080
# Accept the self-signed certificate warning
# Login with: admin / <password from above>
```

**TIP:** Keep this port-forward running in a separate terminal. You'll want the UI open while you do the next exercises.

---

## Step 5: First, Uninstall the Helm Release

**WHY:** Right now, `helm install` owns the resources in the `dev` namespace. We want ArgoCD to take over. Having both manage the same resources causes conflicts (you saw this in Phase 1 with the field ownership error). Clean slate.

```powershell
helm uninstall platform -n dev
kubectl get pods -n dev
# Should be empty (or only terminating pods)
```

---

## Step 6: Create the ArgoCD Application

**WHY:** This tells ArgoCD "watch this Git repo, render the Helm chart, and deploy it to the dev namespace." After this, ArgoCD owns the deployment lifecycle.

```powershell
# Apply the Application manifest
kubectl apply -f c:\Learning\Cloud_engineer\argocd\applications\minikube-helm.yaml

# Check the application status
kubectl get applications -n argocd
```

Now open the ArgoCD UI (https://localhost:8080). You should see `platform-dev` appear. Click on it — you'll see a visual tree of all Kubernetes resources (Deployments, Services, Pods).

**Watch the sync happen:** ArgoCD will clone your GitHub repo, render the Helm chart, and apply it to the `dev` namespace. Within a minute or two, your pods should be running.

```powershell
# Verify pods are back
kubectl get pods -n dev

# Verify the app via ArgoCD CLI (if you want)
kubectl get applications platform-dev -n argocd -o wide
```

---

## Exercise 1: The Magic of GitOps — Change Code, Watch It Deploy

**WHY:** This is the core GitOps experience. You push a change to Git, and the cluster updates automatically. No `kubectl apply`, no `helm upgrade`.

### 1a: Change a value in Git

Edit `helm/gitops-platform/values.yaml` on your machine — change the replica count:

```yaml
frontend:
  replicas: 2    # was 1
```

Commit and push:

```powershell
git add helm/gitops-platform/values.yaml
git commit -m "Scale frontend to 2 replicas"
git push
```

### 1b: Watch ArgoCD detect and sync

Open the ArgoCD UI. Within 3 minutes (default poll interval), ArgoCD will detect the change and show the app as "OutOfSync". If auto-sync is enabled (it is in our config), it will automatically apply the change.

```powershell
# Or watch from the terminal
kubectl get pods -n dev -w
# You'll see a second frontend pod appear
```

**INTERVIEW POINT:** "How does a change get deployed?" — Developer pushes to Git, ArgoCD detects the drift, syncs the cluster. No manual intervention.

### 1c: Force an immediate sync (don't want to wait 3 min)

```powershell
# Install ArgoCD CLI (if not installed)
# Download from: https://argo-cd.readthedocs.io/en/stable/cli_installation/

# Or trigger sync via kubectl
kubectl patch application platform-dev -n argocd --type merge -p '{\"operation\":{\"initiatedBy\":{\"username\":\"admin\"},\"sync\":{\"revision\":\"HEAD\"}}}'

# Simpler: use the ArgoCD UI — click "Sync" button on the application
```

---

## Exercise 2: Self-Heal — ArgoCD Reverts Manual Changes

**WHY:** In production, someone might run a `kubectl` command directly. Self-heal ensures the cluster always matches Git.

```powershell
# Manually scale frontend to 5 replicas (bypassing Git)
kubectl scale deployment frontend --replicas=5 -n dev

# Watch what happens
kubectl get pods -n dev -w
```

ArgoCD detects the drift (5 replicas vs 2 in Git) and reverts it back to 2. This happens within seconds because `selfHeal: true` is set.

**INTERVIEW POINT:** "What happens if someone runs kubectl edit on a production deployment?" — ArgoCD detects the drift and reverts the manual change to match Git.

---

## Exercise 3: See the Diff Before Syncing

**WHY:** In real teams, you want to review what ArgoCD will change before it applies.

```powershell
# Make a change in values.yaml but DON'T push yet
# Edit helm/gitops-platform/values.yaml:
#   orderService.replicas: 2

# Commit and push
git add helm/gitops-platform/values.yaml
git commit -m "Scale order-service to 2 replicas"
git push
```

In the ArgoCD UI:
1. Click on `platform-dev`
2. Click "App Diff" — you'll see exactly what will change
3. The diff shows the Deployment manifest changing from 1 to 2 replicas

This is the audit trail. Every change is a Git commit. Every sync is traceable.

---

## Exercise 4: Rollback via Git Revert

**WHY:** With GitOps, rollback is `git revert` — not `helm rollback` or `kubectl rollout undo`. Git history IS your deployment history.

```powershell
# Revert the last commit (the replica change)
git revert HEAD --no-edit
git push

# Watch ArgoCD sync the reverted state
kubectl get pods -n dev -w
# Replicas go back to the previous count
```

**INTERVIEW POINT:** "How do you rollback a bad deployment?" — `git revert` the commit. ArgoCD syncs the reverted state. Complete audit trail in Git history.

---

## Exercise 5: Application Health & Degraded State

**WHY:** ArgoCD doesn't just sync — it monitors health. If pods crash, it shows "Degraded."

```powershell
# Deploy a broken image tag (push via Git)
# Edit helm/gitops-platform/values.yaml:
#   frontend.tag: "broken"

git add helm/gitops-platform/values.yaml
git commit -m "Deploy broken frontend image"
git push
```

In the ArgoCD UI:
- The app will show "Synced" (manifests applied) but "Degraded" (pods failing)
- Click on the frontend Deployment — you'll see the pod in `ImagePullBackOff`
- This is the difference between "synced" and "healthy"

Fix it:

```powershell
# Revert the broken change
git revert HEAD --no-edit
git push
# ArgoCD syncs, pods recover
```

---

## Exercise 6: Inspect the ArgoCD Application Resource

**WHY:** Understanding the Application spec is key for interviews.

```powershell
# See the full Application resource
kubectl get application platform-dev -n argocd -o yaml

# Key fields to understand:
# spec.source.repoURL     — which Git repo to watch
# spec.source.path         — which directory in the repo
# spec.destination         — which cluster/namespace to deploy to
# spec.syncPolicy.automated — auto-sync enabled?
# status.sync.status       — Synced / OutOfSync
# status.health.status     — Healthy / Degraded / Progressing
```

---

## Exercise 7: Multiple Environments (Optional)

**WHY:** Real teams deploy the same app to dev/staging/prod.

```powershell
# Create a values-staging.yaml
# (copy values.yaml, change replicas to 2, nodePort to 30089)

# Create a second ArgoCD Application for staging
# (copy minikube-helm.yaml, change name, namespace, valueFiles)

# Apply it
kubectl apply -f argocd/applications/staging-helm.yaml

# Now you have two environments managed by ArgoCD
# Each watches the same repo but uses different values
```

---

## Key Concepts Cheat Sheet

| Concept | What It Means |
|---------|--------------|
| **Synced** | Cluster matches Git (desired state = live state) |
| **OutOfSync** | Git changed but cluster hasn't caught up yet |
| **Healthy** | All pods running and passing health checks |
| **Degraded** | Synced but pods are failing (CrashLoop, ImagePull) |
| **Progressing** | Sync in progress (rolling update happening) |
| **Self-Heal** | ArgoCD reverts manual `kubectl` changes |
| **Prune** | ArgoCD deletes resources removed from Git |
| **Auto-Sync** | Sync happens automatically on Git change |
| **Manual Sync** | Requires clicking "Sync" (used for prod) |
| **App of Apps** | One ArgoCD app manages other ArgoCD apps |

---

## How This Maps to Interview Questions

| Interview Question | What You Learned |
|---|---|
| "What is GitOps?" | Git is the source of truth. ArgoCD syncs cluster to Git. |
| "How do you deploy a change?" | Push to Git. ArgoCD auto-syncs. |
| "How do you rollback?" | `git revert`. ArgoCD syncs the reverted state. |
| "What if someone runs kubectl edit?" | Self-heal reverts it to match Git. |
| "How do you promote dev to prod?" | PR to update prod values. Manual sync for prod. |
| "How do you monitor deployments?" | ArgoCD UI shows sync status + health. |
| "What's the difference between synced and healthy?" | Synced = manifests applied. Healthy = pods running. |

---

## What's Next?

Phase 3 will cover:
- GitHub Actions CI pipeline (free, 2000 min/month)
- Build images on push, push to GitHub Container Registry (free)
- Auto-update image tags in the Helm values
- Full CI/CD loop: push code → build image → update Git → ArgoCD syncs
