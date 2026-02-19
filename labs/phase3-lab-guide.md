# Phase 3: Mastering GitHub Actions & CI/CD

## What You Will Build

By the end of this phase you will have three workflow files:

```
.github/workflows/
├── ci.yaml           ← already written, just needs committing
├── pr-checks.yaml    ← you will create this (Exercise 2)
└── deploy.yaml       ← you will create this (Exercise 5)
```

The final pipeline will work like this:
```
You open a PR  →  pr-checks.yaml runs  (lint + build + security scan)
PR merges      →  ci.yaml runs         (build image, push to GHCR)
CI finishes    →  deploy.yaml runs     (promote dev → staging → prod)
```

---

## Before You Start — Key Concepts

### What is a GitHub Actions workflow?
A YAML file in `.github/workflows/`. GitHub reads it and runs it automatically on events
(push, PR, schedule). Each file = one workflow.

### Anatomy of every workflow:
```yaml
name: My Workflow        # name shown in GitHub Actions tab

on:                      # WHEN to run
  push:
    branches: [main]

jobs:                    # WHAT to run
  my-job:
    runs-on: ubuntu-latest   # GitHub spins up a fresh Ubuntu VM
    steps:
      - name: Step 1
        run: echo "hello"
      - name: Step 2
        run: echo "world"
```

### Key variables you'll see everywhere:
| Variable | Value | Meaning |
|----------|-------|---------|
| `github.actor` | `jithin2` | Who triggered the run |
| `github.sha` | `abc1234...` | Full commit SHA |
| `github.ref` | `refs/heads/main` | Branch that triggered |
| `secrets.GITHUB_TOKEN` | `***` | Auto-created token, no setup needed |
| `needs.build.outputs.tag` | `abc1234` | Output from another job |

---

## Exercise 1: Commit the CI Workflow

**WHY:** The `ci.yaml` file already exists locally but was never pushed to GitHub.
GitHub Actions only reads workflows that are committed to the repo.

### Step 1 — Check what's waiting to be committed
```powershell
git status
```
You should see `ci.yaml` and the lab guides as untracked files.

### Step 2 — Enable write permissions on GitHub
Go to your repo → **Settings** → **Actions** → **General**
→ "Workflow permissions" → select **Read and write permissions** → **Save**

**WHY:** The CI workflow needs to push Docker images (packages) and commit
`values-ghcr.yaml` back to the repo. Without write permission it will fail.

### Step 3 — Commit and push
```powershell
git add .github/workflows/ci.yaml labs/phase3-lab-guide.md labs/phase4-lab-guide.md
git commit -m "Add Phase 3: CI pipeline and lab guides"
git push
```

### Step 4 — Check GitHub
Go to your repo → **Actions** tab.
You'll see the workflow listed but it won't have run yet — because `services/**` files
didn't change in this commit (the trigger condition).

### Step 5 — Understand the ci.yaml trigger
Open `.github/workflows/ci.yaml` and find this section:
```yaml
on:
  push:
    branches: [main]
    paths:
      - "services/**"
```
**WHY `paths`:** CI only runs when service code changes. Pushing docs, lab guides, or
Helm values does NOT trigger a build. This saves your free CI minutes (2000/month).

---

## Exercise 2: Create the PR Checks Workflow

**WHY:** In real teams, nobody pushes directly to `main`. Every change goes through a
Pull Request. This workflow is the gatekeeper — PR cannot merge unless these checks pass.

### Step 1 — Create the file
Create a new file: `.github/workflows/pr-checks.yaml`

```yaml
name: PR Checks

on:
  pull_request:
    branches: [main]

jobs:

  # ── CHECK 1: Go code style ──────────────────────────────────
  lint-go:
    name: Lint Go (frontend)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true          # caches go modules — faster on repeat runs

      - name: go vet (checks for bugs)
        working-directory: services/frontend
        run: go vet ./...

      - name: gofmt (checks formatting)
        working-directory: services/frontend
        run: |
          if [ "$(gofmt -l . | wc -l)" -gt 0 ]; then
            echo "These files need formatting:"
            gofmt -l .
            exit 1
          fi

  # ── CHECK 2: Python code style ──────────────────────────────
  lint-python:
    name: Lint Python (order + product)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install flake8
        run: pip install flake8

      - name: Lint order-service
        run: flake8 services/order-service/main.py --max-line-length=120

      - name: Lint product-service
        run: flake8 services/product-service/main.py --max-line-length=120

  # ── CHECK 3: Docker images build successfully ─────────────
  build-images:
    name: Build Docker images
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3

      - name: Build frontend
        uses: docker/build-push-action@v5
        with:
          context: services/frontend
          push: false          # on PRs we build but do NOT push
          tags: frontend:test

      - name: Build order-service
        uses: docker/build-push-action@v5
        with:
          context: services/order-service
          push: false
          tags: order-service:test

      - name: Build product-service
        uses: docker/build-push-action@v5
        with:
          context: services/product-service
          push: false
          tags: product-service:test

  # ── CHECK 4: Security scan ───────────────────────────────
  security-scan:
    name: Security scan (Trivy)
    runs-on: ubuntu-latest
    needs: build-images        # runs AFTER build-images succeeds
    steps:
      - uses: actions/checkout@v4

      - name: Build image for scanning
        run: docker build -t scan-target services/frontend

      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: scan-target
          format: table
          exit-code: '0'       # '0' = warn only. Change to '1' to block on HIGH vulns
          severity: HIGH,CRITICAL

  # ── CHECK 5: Helm chart is valid ─────────────────────────
  validate-helm:
    name: Validate Helm chart
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Helm
        uses: azure/setup-helm@v4

      - name: helm lint
        run: helm lint helm/gitops-platform

      - name: helm template (dry run)
        run: helm template platform helm/gitops-platform
```

### Step 2 — Commit the file
```powershell
git add .github/workflows/pr-checks.yaml
git commit -m "Add PR checks workflow (lint, build, security, helm)"
git push
```

### Step 3 — Set up branch protection
Go to your repo → **Settings** → **Branches** → **Add branch ruleset**
- Name: `main-protection`
- Target branches: `main`
- Enable: **Require a pull request before merging**
- Enable: **Require status checks to pass**
  - Add: `Lint Go (frontend)`
  - Add: `Lint Python (order + product)`
  - Add: `Build Docker images`
- Click **Create**

**WHY:** Now GitHub will refuse to merge a PR if any check fails.
This is the industry standard — broken code cannot reach `main`.

---

## Exercise 3: Test the PR Workflow

**WHY:** Hands-on — create a real PR and watch all 5 checks run.

### Step 1 — Create a feature branch
```powershell
git checkout -b feature/version-endpoint
```
**WHY a branch:** You never work directly on `main`. Each feature/fix gets its own branch.

### Step 2 — Add a /version endpoint to the frontend
Open `services/frontend/main.go`. Find where the HTTP handlers are set up (look for
`http.HandleFunc`) and add this new route:

```go
http.HandleFunc("/version", func(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    fmt.Fprintf(w, `{"version": "1.1.0", "service": "frontend"}`)
})
```

### Step 3 — Commit and push the branch
```powershell
git add services/frontend/main.go
git commit -m "feat: add /version endpoint"
git push origin feature/version-endpoint
```

### Step 4 — Open a Pull Request
Go to your GitHub repo. You'll see a yellow banner:
**"feature/version-endpoint had recent pushes — Compare & pull request"**

Click it → add a description → click **Create pull request**.

### Step 5 — Watch the checks run
Scroll to the bottom of the PR. You'll see the 5 checks running:
- `Lint Go (frontend)` — checking go vet and formatting
- `Lint Python` — checking flake8
- `Build Docker images` — verifying all 3 Dockerfiles build
- `Security scan` — Trivy scanning the frontend image
- `Validate Helm chart` — helm lint

All should pass (green tick). If any fail, fix the code and push again —
the checks re-run automatically.

### Step 6 — Merge the PR
Once all checks are green → click **Merge pull request** → **Confirm merge**.

After merging:
```powershell
# Switch back to main and pull the merged changes
git checkout main
git pull
```

---

## Exercise 4: Trigger the CI Build

**WHY:** The PR merged changes to `services/frontend/main.go` — this triggers `ci.yaml`
because it matches `paths: services/**`.

### Step 1 — Watch GitHub Actions
Go to **Actions** tab → you should see "CI — Build & Push Images" running.

Click on it and expand each job:
- `detect-changes` — identifies only `frontend: true` changed
- `build-and-push` — builds frontend image, pushes to GHCR
- `update-manifests` — updates `values-ghcr.yaml` with new image tag

### Step 2 — Check the image in GHCR
After the pipeline completes, go to:
`https://github.com/jithin2?tab=packages`

You should see `gke-gitops-platform/frontend` as a package with your image tags.

### Step 3 — Check the auto-commit
Go to your repo → **Code** tab → look at recent commits.
You should see a commit from `github-actions[bot]`:
```
ci: update image tags to abc1234 [skip ci]
```

Pull it locally:
```powershell
git pull
cat helm/gitops-platform/values-ghcr.yaml
```

You'll see the new image tag written by CI.

**WHY `[skip ci]`:** Without this, the CI bot's commit would trigger CI again → infinite loop.
`[skip ci]` tells GitHub Actions to skip this push.

---

## Exercise 5: Set Up Secrets & Environments

**WHY:** Real deployments need different configs per environment (dev/staging/prod).
GitHub Environments let you have separate secrets per environment AND add approval gates.

### Step 1 — Create GitHub Environments
Go to your repo → **Settings** → **Environments** → **New environment**

Create three environments:
1. **dev** — no protection rules
2. **staging** — no protection rules
3. **prod** — click **Required reviewers** → add yourself → Save

### Step 2 — Add a secret to each environment
For each environment, click on it → **Add secret**:
- Name: `DEPLOY_TARGET`
- `dev` value: `kubernetes://dev`
- `staging` value: `kubernetes://staging`
- `prod` value: `kubernetes://prod`

**WHY:** Same secret name, different value per environment. The workflow uses
`${{ secrets.DEPLOY_TARGET }}` — GitHub injects the right value based on which
environment the job is running in.

### Step 3 — Add a repository-level secret (test)
Go to **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `MY_TEST_SECRET`
- Value: `hello-secret-world`

**WHY the difference:**
- **Repository secret** — available to ALL workflows in the repo
- **Environment secret** — only available when a job targets that specific environment

---

## Exercise 6: Create the Deploy Workflow

**WHY:** CI builds the image. This deploy workflow promotes it through environments.
Dev auto-deploys. Staging auto-deploys after dev. Prod requires your manual approval.

### Step 1 — Create the file
Create `.github/workflows/deploy.yaml`:

```yaml
name: Deploy

on:
  # Runs automatically after CI completes on main
  workflow_run:
    workflows: ["CI — Build & Push Images"]
    types: [completed]
    branches: [main]

  # Also allows manual trigger with custom inputs
  workflow_dispatch:
    inputs:
      environment:
        description: 'Which environment to deploy to?'
        required: true
        type: choice
        options: [dev, staging, prod]

jobs:

  # ── DEPLOY TO DEV (automatic) ──────────────────────────────
  deploy-dev:
    name: Deploy to Dev
    runs-on: ubuntu-latest
    # Only run if CI passed (not if it failed)
    if: ${{ github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch' }}
    environment: dev       # injects dev secrets, shows in dev deployment history
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: Show what's being deployed
        run: |
          echo "=== Deploying to DEV ==="
          echo "Target: ${{ secrets.DEPLOY_TARGET }}"
          echo "Image tags:"
          cat helm/gitops-platform/values-ghcr.yaml || echo "values-ghcr.yaml not found yet"

      - name: Confirm ArgoCD will auto-sync
        run: |
          echo "ArgoCD watches the repo and will sync within 3 minutes"
          echo "Run: kubectl get pods -n dev -w  (to watch rollout)"

  # ── DEPLOY TO STAGING (after dev) ─────────────────────────
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: deploy-dev      # only runs after deploy-dev succeeds
    environment: staging   # injects staging secrets
    steps:
      - name: Deploy to staging
        run: |
          echo "=== Deploying to STAGING ==="
          echo "Target: ${{ secrets.DEPLOY_TARGET }}"

  # ── DEPLOY TO PROD (requires approval) ────────────────────
  deploy-prod:
    name: Deploy to Prod
    runs-on: ubuntu-latest
    needs: deploy-staging  # only runs after staging succeeds
    environment: prod      # PAUSES HERE and waits for manual approval
    steps:
      - name: Deploy to prod
        run: |
          echo "=== Deploying to PRODUCTION ==="
          echo "Target: ${{ secrets.DEPLOY_TARGET }}"
          echo "Approved by: ${{ github.actor }}"
```

### Step 2 — Commit the file
```powershell
git add .github/workflows/deploy.yaml
git commit -m "Add deploy workflow with dev/staging/prod environments"
git push
```

### Step 3 — Trigger a full pipeline run
Make a small change to any service file to trigger CI, which then triggers deploy:

```powershell
git checkout -b feature/test-full-pipeline
# Edit services/order-service/main.py — add a comment at the top
git add services/order-service/main.py
git commit -m "test: trigger full pipeline"
git push origin feature/test-full-pipeline
```

Open a PR → watch `pr-checks.yaml` run → merge the PR.

### Step 4 — Watch the full flow

1. **Actions tab** → `CI — Build & Push Images` runs → builds order-service image
2. **Actions tab** → `Deploy` workflow triggers automatically
3. `Deploy to Dev` runs (automatic)
4. `Deploy to Staging` runs (automatic, after dev)
5. `Deploy to Prod` **pauses** — you get an email notification

### Step 5 — Approve the prod deployment
Go to **Actions** → click the `Deploy` run → you'll see it waiting at `Deploy to Prod`.
Click **Review deployments** → check `prod` → click **Approve and deploy**.

Watch the prod job complete.

**INTERVIEW POINT:** "How do you control prod deployments?" — GitHub Environments with
required reviewers. Dev deploys automatically. Staging deploys after dev. Prod requires
explicit approval. No one can skip this — it's enforced by GitHub.

---

## Exercise 7: Manually Trigger a Deployment

**WHY:** In an emergency (hotfix, rollback), you may need to deploy a specific version
without waiting for the full pipeline.

### Step 1 — Go to Actions tab
Click on **Deploy** workflow → click **Run workflow** button (top right).

You'll see a dropdown:
- "Which environment to deploy to?" → select `staging`

Click **Run workflow**.

### Step 2 — Watch it run
The workflow runs but only for staging (skips dev and prod).

This is how you do targeted deployments — useful for:
- Hotfixes that need to skip the full PR flow
- Re-deploying a specific version to an environment

---

## Exercise 8: Advanced — Reusable Workflows

**WHY:** If you have multiple services, you'd copy-paste the same build steps 3 times.
Reusable workflows let you define build logic once and call it like a function.

### Step 1 — Create a reusable build workflow
Create `.github/workflows/reusable-build.yaml`:

```yaml
name: Reusable Build

on:
  workflow_call:            # this keyword makes it callable from other workflows
    inputs:
      service:
        required: true
        type: string        # e.g. "frontend"
      context:
        required: true
        type: string        # e.g. "services/frontend"
    outputs:
      image_tag:
        description: "Built image tag"
        value: ${{ jobs.build.outputs.tag }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.tag.outputs.sha_short }}
    steps:
      - uses: actions/checkout@v4

      - name: Generate tag
        id: tag
        run: echo "sha_short=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          context: ${{ inputs.context }}
          push: true
          tags: ghcr.io/${{ github.repository_owner }}/gke-gitops-platform/${{ inputs.service }}:${{ steps.tag.outputs.sha_short }}
```

### Step 2 — Call it from another workflow
```yaml
# In any other workflow:
jobs:
  build-frontend:
    uses: ./.github/workflows/reusable-build.yaml
    with:
      service: frontend
      context: services/frontend

  build-order:
    uses: ./.github/workflows/reusable-build.yaml
    with:
      service: order-service
      context: services/order-service
```

Both jobs run in parallel. Each uses the same build logic without duplication.

---

## Summary — What You Built

```
.github/workflows/
├── ci.yaml               ✅ builds images on push to main (selective)
├── pr-checks.yaml        ✅ lint + build + security + helm on every PR
├── deploy.yaml           ✅ dev → staging → prod with manual approval for prod
└── reusable-build.yaml   ✅ reusable build logic (DRY principle)
```

### Full pipeline flow:
```
Feature branch created
      │
      ▼
PR opened → pr-checks.yaml runs (lint, build, scan, helm)
      │
      ▼
PR merged to main → ci.yaml runs (build image, push to GHCR, update values)
      │
      ▼
deploy.yaml triggers → deploys to dev (auto) → staging (auto) → prod (manual approval)
      │
      ▼
ArgoCD detects values-ghcr.yaml changed → syncs cluster → new pods running
```

---

## Key Interview Points

| Question | Answer |
|----------|--------|
| "Describe your CI/CD pipeline" | PR checks → merge → build image → push to GHCR → update values → ArgoCD deploys |
| "Why use paths filter?" | Only build changed services — saves CI minutes, faster feedback |
| "How do you manage secrets?" | GitHub Secrets — repo level for shared, environment level for env-specific |
| "How do you control prod?" | GitHub Environments with required reviewers — prod requires manual approval |
| "What is [skip ci]?" | Prevents infinite loop when CI bot commits back to the repo |
| "What checks run on PRs?" | Lint (go vet, flake8), Docker builds, Trivy security scan, Helm lint |
| "What is a reusable workflow?" | A workflow triggered by `workflow_call` — called like a function from other workflows |
| "Why never use `latest` in prod?" | Not immutable — you can't trace what's running. Use Git SHA tags |

---

## What's Next — Phase 4

Monitoring & Observability:
- Prometheus + Loki + Grafana (PLG stack) on Minikube
- Custom dashboards for your services
- Alerting rules
- SLOs and error budgets
