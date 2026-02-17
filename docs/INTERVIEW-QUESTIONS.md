# Interview Questions & Answers

Scenario-based Q&A covering Kubernetes, GitOps/ArgoCD, Terraform, and GCP — all grounded in this platform's architecture.

---

## Kubernetes

**Q1: A pod is stuck in `CrashLoopBackOff`. How do you diagnose it?**
Check `kubectl describe pod <name>` for events and exit codes, then `kubectl logs <pod> --previous` for the last crash output. Common causes: misconfigured env vars, failed health probes, OOMKilled (check `lastState.terminated.reason`).

**Q2: What's the difference between a readiness probe and a liveness probe?**
Liveness determines if a container should be restarted. Readiness determines if it should receive traffic. A failing readiness probe removes the pod from Service endpoints; a failing liveness probe kills and restarts the container.

**Q3: Why does this project use `ClusterIP` services instead of `NodePort` or `LoadBalancer` for backend services?**
Backend services only need to be reachable within the cluster. ClusterIP avoids exposing internal services externally. The frontend is the only public entry point, exposed via Ingress backed by a GCP HTTP(S) Load Balancer.

**Q4: A deployment rollout is stuck. How do you troubleshoot?**
`kubectl rollout status deployment/<name>`, then check if new pods are failing to schedule (`Pending` — resource constraints, node affinity) or start (`CrashLoopBackOff`, image pull errors). `kubectl get events --sort-by=.lastTimestamp` gives a timeline.

**Q5: Explain how HPA works in this platform.**
HPA watches CPU/memory metrics from the metrics-server. When average utilization exceeds the target (e.g., 70% CPU), it increases replica count up to `maxReplicas`. It scales down after a stabilization window (default 5 min) to avoid flapping.

**Q6: Why are PodDisruptionBudgets only in staging and prod overlays?**
Dev runs a single replica — a PDB with `minAvailable: 1` would block voluntary disruptions like node drains entirely. In staging/prod, PDBs ensure that rolling updates and node maintenance don't take all replicas offline simultaneously.

**Q7: What happens if a node running your pods gets preempted (spot instance)?**
GKE sends a termination notice (~30s). The kubelet starts graceful shutdown — sends SIGTERM, respects `terminationGracePeriodSeconds`. The PDB ensures enough replicas remain. The scheduler places replacement pods on available nodes.

**Q8: How do NetworkPolicies work in this project?**
Each service has a deny-all ingress default, then explicit rules allow only expected traffic paths (frontend -> order-service, frontend -> product-service, order-service -> product-service). Requires a CNI that supports NetworkPolicy (GKE Dataplane V2 does).

**Q9: A pod is in `Pending` state for 5 minutes. What could cause this?**
Insufficient cluster resources (CPU/memory), node affinity/anti-affinity rules can't be satisfied, PVC can't be bound, or the cluster autoscaler hasn't scaled up yet. Check `kubectl describe pod` events for the scheduler's reason.

**Q10: What's the difference between `requests` and `limits` for resources?**
Requests are guaranteed — the scheduler uses them for bin-packing. Limits are the ceiling — exceeding memory limits causes OOMKill, exceeding CPU limits causes throttling. This project sets both per-environment via Kustomize patches.

**Q11: How does anti-affinity work in the prod overlay?**
`requiredDuringSchedulingIgnoredDuringExecution` with `topologyKey: kubernetes.io/hostname` ensures no two pods of the same service land on the same node. This survives single-node failure without losing all replicas.

**Q12: How would you debug DNS resolution failures inside a pod?**
`kubectl exec` into a debug pod, run `nslookup <service>.<namespace>.svc.cluster.local`. Check if CoreDNS pods are running (`kube-system` namespace). Look at CoreDNS logs for errors. Verify the pod's `/etc/resolv.conf` has the correct search domains.

**Q13: What's the purpose of the `terminationGracePeriodSeconds` field?**
It gives a container time to finish in-flight requests after receiving SIGTERM before the kubelet sends SIGKILL. Default is 30s. Critical for graceful shutdown of services with long-running requests.

**Q14: How do rolling updates work in Kubernetes?**
The Deployment controller creates new ReplicaSet pods before terminating old ones, governed by `maxSurge` and `maxUnavailable`. It waits for readiness probes to pass before continuing. If new pods fail, the rollout stalls (and can be rolled back with `kubectl rollout undo`).

**Q15: Why run containers as non-root with a read-only filesystem?**
Limits blast radius of container compromise. An attacker can't install tools, modify binaries, or escalate privileges. The application writes only to explicitly mounted volumes (e.g., `/tmp`).

---

## GitOps & ArgoCD

**Q16: What is GitOps and why use it?**
Git is the single source of truth for desired cluster state. All changes go through Git commits (auditable, reversible). An operator (ArgoCD) continuously reconciles the cluster to match Git. No manual `kubectl apply` in the delivery path.

**Q17: How does ArgoCD detect changes?**
ArgoCD polls the Git repo at a configurable interval (default 3 min) or receives webhook notifications. It compares the rendered manifests from Git against the live cluster state. Any difference is reported as "OutOfSync."

**Q18: Someone ran `kubectl edit` on a production deployment. What happens?**
ArgoCD detects drift between live state and Git. It reports the app as OutOfSync. If auto-sync is enabled, ArgoCD reverts the manual change. If not, the dashboard shows the diff until someone manually syncs or the Git state is updated to match.

**Q19: Explain the app-of-apps pattern used here.**
A single root ArgoCD Application points to a directory (`argocd/apps/`) containing Application manifests for each environment. ArgoCD syncs the root app, which creates/manages all child Applications. Adding an environment = adding a YAML file.

**Q20: How do you roll back a bad deployment with GitOps?**
`git revert <commit>` and push. ArgoCD detects the reverted manifests and syncs the cluster back. Alternatively, use `argocd app rollback` for immediate rollback to a previous sync revision, but the Git commit is still the recommended path for auditability.

**Q21: What's the purpose of the AppProject resource?**
It defines RBAC boundaries — which source repos ArgoCD can pull from, which clusters/namespaces it can deploy to, and which resource kinds are allowed. Prevents a misconfigured Application from deploying to unintended namespaces or clusters.

**Q22: How would you promote a change from dev to prod?**
Update the image tag in `k8s/overlays/dev/kustomization.yaml` (CI does this). After validation, open a PR updating the same tag in `staging`, then `prod`. Each merge triggers ArgoCD sync for that environment. PRs provide review gates.

**Q23: ArgoCD shows an app as "Degraded." What do you check?**
The app synced successfully but pod health checks are failing. Check pod status (`kubectl get pods`), describe pods for events, check logs. Common causes: bad config, dependency unavailable, failing readiness probes.

**Q24: What's the difference between ArgoCD sync and refresh?**
Refresh re-reads the Git repo to compare desired vs. live state (detects drift). Sync actually applies the desired state to the cluster. Refresh is read-only; sync makes changes.

**Q25: Why use Kustomize instead of Helm with ArgoCD?**
Kustomize produces plain YAML — what you see in Git is exactly what gets applied. No templating engine to debug. ArgoCD natively supports Kustomize rendering. For this project's use case (same base, small per-env deltas), Kustomize is simpler.

**Q26: How does CI update the image tag without manual intervention?**
GitHub Actions builds the image, pushes it to Artifact Registry, then runs `kustomize edit set image` against the target overlay's `kustomization.yaml`. It commits and pushes the change. ArgoCD picks up the new commit.

**Q27: What happens if ArgoCD itself goes down?**
Running workloads continue unaffected — ArgoCD is a control plane, not a data plane. No new syncs happen until ArgoCD recovers. Manual `kubectl` commands still work. ArgoCD is deployed as a Deployment with multiple replicas for HA.

**Q28: How do you handle secrets in a GitOps workflow?**
Don't store plaintext secrets in Git. Options: Sealed Secrets (encrypted in Git, decrypted in-cluster), External Secrets Operator (syncs from GCP Secret Manager), or SOPS with age/KMS encryption. This project uses Workload Identity to avoid key-based auth entirely.

**Q29: What is self-heal in ArgoCD?**
When enabled, ArgoCD automatically reverts any manual changes to the live cluster that cause drift from Git. Combined with auto-sync, it ensures the cluster always converges to the Git-declared state.

**Q30: How would you handle a canary deployment with this setup?**
Options: Argo Rollouts (replaces Deployment with a Rollout resource, supports canary with traffic splitting), or a manual approach using separate canary Deployments with weighted Ingress backends. Argo Rollouts integrates natively with ArgoCD.

---

## Terraform & Infrastructure

**Q31: Why use a remote backend (GCS) for Terraform state?**
Local state files can't be shared across team members, aren't locked during concurrent runs (risking corruption), and aren't versioned. GCS provides locking, versioning, encryption at rest, and team-wide access.

**Q32: What happens if two people run `terraform apply` simultaneously?**
The GCS backend supports state locking. The second run will fail to acquire the lock and abort. This prevents concurrent modifications that could corrupt state or create conflicting resources.

**Q33: A `terraform plan` shows a resource being destroyed unexpectedly. What do you do?**
Don't apply. Investigate why — someone may have removed it from config, a data source may have changed, or a provider upgrade may have altered resource schemas. Use `terraform state show <resource>` and `terraform plan -target=<resource>` to isolate.

**Q34: Why is the GKE cluster configured as private?**
Nodes have no public IPs, reducing attack surface. The API server has restricted access. All egress goes through Cloud NAT. This is Google's recommended security posture for production GKE clusters.

**Q35: Explain Workload Identity in this project.**
A Kubernetes ServiceAccount is annotated with a GCP service account email. GKE's metadata server intercepts token requests and returns GCP credentials via OIDC federation. Pods authenticate to GCP APIs without any exported keys.

**Q36: How does Cloud NAT work here?**
Private nodes have no external IPs but need outbound access (pull images, reach APIs). Cloud Router + Cloud NAT provides SNAT for outbound connections. No inbound access is allowed — it's egress-only.

**Q37: What are secondary IP ranges in the VPC and why are they needed?**
GKE uses separate IP ranges for pods and services (VPC-native networking). This enables alias IPs, which means pods get routable IPs within the VPC. Required for private clusters and enables more efficient routing than bridge-based networking.

**Q38: How would you import an existing GCP resource into Terraform?**
`terraform import <resource_address> <resource_id>`, then write the matching HCL configuration. Run `terraform plan` to verify no diff. For bulk imports, use `terraform import` blocks (Terraform 1.5+).

**Q39: What's the difference between `terraform taint` and `terraform apply -replace`?**
Both force recreation of a resource. `taint` is deprecated in favor of `-replace=<resource>` which is more explicit and doesn't persist between plan/apply cycles. Use when a resource is in a bad state that in-place update can't fix.

**Q40: How do you manage multiple environments with Terraform?**
Options: separate `.tfvars` files per env, Terraform workspaces, or separate state files with a shared module. This project uses a single Terraform config with variables — the env-specific configuration lives in Kustomize overlays instead.

**Q41: A Terraform apply fails halfway through. What's the state?**
Terraform state reflects what was actually created. Successfully created resources are in state; failed ones aren't. Running `terraform apply` again will retry only the failed/missing resources. State is updated atomically per resource.

**Q42: Why use `google_container_node_pool` as a separate resource instead of inline?**
Separate resources allow independent lifecycle management — you can update node pools without affecting the cluster control plane. Inline node pools force cluster recreation on certain changes.

**Q43: How do you handle Terraform provider version upgrades safely?**
Pin provider versions in `required_providers`. Upgrade in a branch, run `terraform init -upgrade`, then `terraform plan` to review changes. Some upgrades change resource schemas. Always review the changelog and plan output before applying.

**Q44: What's the purpose of `terraform.tfvars.example`?**
Documents required variables without committing actual values (which may contain project IDs, sensitive config). Users copy it to `terraform.tfvars` (which is gitignored) and fill in their values.

**Q45: How would you destroy only the node pool without affecting the rest of the infra?**
`terraform destroy -target=google_container_node_pool.<name>`. Use targeted operations carefully — they can leave state inconsistent if dependencies aren't considered.

---

## GCP & Networking

**Q46: Your pods can't pull images from Artifact Registry. How do you troubleshoot?**
Check: 1) Node service account has `artifactregistry.reader` role. 2) Private Google Access is enabled on the subnet (needed for private nodes). 3) DNS resolves `*.pkg.dev`. 4) Cloud NAT is working if accessing public endpoints.

**Q47: Explain how the GCP HTTP(S) Load Balancer integrates with GKE.**
The GKE Ingress controller creates a GCP HTTP(S) LB automatically when an Ingress resource is created. It provisions a forwarding rule, URL map, backend services (mapped to NEGs or instance groups), and health checks. TLS termination happens at the LB.

**Q48: What's Private Google Access and why is it enabled?**
Allows VMs without external IPs to reach Google APIs and services (like Artifact Registry, GCS) via internal IP routes. Without it, private nodes can't interact with GCP services even through Cloud NAT.

**Q49: How does GKE cluster autoscaler differ from HPA?**
HPA scales pods horizontally based on metrics. Cluster autoscaler scales nodes — it adds nodes when pods are unschedulable due to resource constraints and removes nodes when they're underutilized. They work together: HPA creates demand, autoscaler provides capacity.

**Q50: A pod's Workload Identity authentication to GCS is failing. What do you check?**
1) KSA is annotated with `iam.gke.io/gcp-service-account`. 2) GCP SA has the IAM binding `roles/iam.workloadIdentityUser` for the KSA. 3) Pod spec references the correct `serviceAccountName`. 4) Workload Identity is enabled on the node pool.

**Q51: What's the difference between a regional and zonal GKE cluster?**
Regional clusters replicate the control plane across 3 zones (HA). Zonal clusters have a single control plane (cheaper, but unavailable during upgrades). This project uses regional for prod reliability.

**Q52: How would you restrict access to the GKE API server?**
Use `master_authorized_networks_config` in Terraform to allowlist specific CIDR ranges. For maximum security, combine with Private Endpoint (no public endpoint) and access via a bastion host or VPN.

**Q53: Cloud NAT is running but pods still can't reach the internet. What's wrong?**
Check: NAT is configured on the correct router/region, the subnet is included in NAT config, NAT IP allocation isn't exhausted, firewall rules aren't blocking egress, and the pod's NetworkPolicy allows egress.

**Q54: How does VPC-native (alias IP) networking benefit GKE?**
Pod IPs are routable within the VPC without encapsulation. Enables direct VPC firewall rules on pod traffic, better performance (no overlay), and is required for private clusters and certain features like Network Endpoint Groups.

**Q55: What's the cost impact of Cloud NAT?**
Charged per VM using NAT + per GB of data processed. For clusters with heavy outbound traffic, costs can add up. Mitigations: cache images locally, use Private Google Access for GCP API traffic (bypasses NAT), and monitor NAT gateway utilization.

---

## CI/CD Pipeline

**Q56: Walk through what happens when a developer pushes to the main branch.**
GitHub Actions triggers: 1) Lint and test code. 2) Build Docker image with commit SHA tag. 3) Push to Artifact Registry. 4) Run `kustomize edit set image` on the target overlay. 5) Commit and push manifest change. 6) ArgoCD detects and syncs.

**Q57: Why tag images with the Git commit SHA instead of `latest`?**
`latest` is mutable — you can't tell which build is running. Commit SHAs are immutable and tie the running image directly to a specific code version. This enables deterministic rollbacks and audit trails.

**Q58: The CI pipeline fails at the image push step. How do you debug?**
Check: authentication to Artifact Registry (Workload Identity Federation for GitHub Actions or service account key), repository exists, correct region, image name format matches `<region>-docker.pkg.dev/<project>/<repo>/<image>`, and network connectivity.

**Q59: How do you prevent the CI manifest commit from triggering another CI run?**
Use a `[skip ci]` tag in the commit message, or configure the workflow to ignore commits that only modify `kustomization.yaml` files. Alternatively, use a dedicated bot account whose commits are excluded from workflow triggers.

**Q60: How would you add a staging gate before prod deployment?**
Require a manual PR approval for prod overlay changes. Optionally, add a GitHub Actions workflow that runs integration tests against staging before allowing the prod PR to merge. ArgoCD can also require manual sync for prod.

---

## Monitoring & Observability

**Q61: Explain the RED method used in the Grafana dashboards.**
Rate (requests per second), Errors (error rate as percentage), Duration (latency distribution). These three signals cover the user-facing health of any request-driven service. Each service dashboard tracks all three.

**Q62: A Prometheus alert fires for "high error rate." What's your response?**
Check which service is affected (alert labels). Look at Grafana dashboards for the error spike timeline. Check pod logs for error details. Check if a recent deployment correlates with the spike. If so, rollback via `git revert`.

**Q63: How does Prometheus discover scrape targets in Kubernetes?**
Kubernetes service discovery. Prometheus uses the K8s API to find pods/services with specific annotations (`prometheus.io/scrape: "true"`, `prometheus.io/port`). As pods come and go, targets are automatically updated.

**Q64: ArgoCD has been out-of-sync for 10+ minutes (alert fires). What do you check?**
ArgoCD UI/CLI for sync status and error messages. Common causes: invalid manifests in Git, RBAC permissions changed, cluster connectivity issues, resource validation failures, or a manual change creating persistent drift.

**Q65: What's the difference between recording rules and alerting rules in Prometheus?**
Recording rules precompute expensive queries and store results as new time series (performance optimization). Alerting rules evaluate expressions and fire alerts when conditions are true for a specified duration.

**Q66: Pod crash loop alert fires. Walk through your triage.**
1) `kubectl get pods` — identify the crashing pod. 2) `kubectl describe pod` — check events, exit codes. 3) `kubectl logs --previous` — last crash output. 4) Check if a recent deploy caused it. 5) Check resource limits (OOMKilled?). 6) Check dependent services (DB down?).

**Q67: How do you monitor cluster autoscaler behavior?**
Autoscaler exposes metrics: `cluster_autoscaler_scaled_up_nodes_total`, `cluster_autoscaler_unschedulable_pods_count`. Also check autoscaler status configmap: `kubectl get cm cluster-autoscaler-status -n kube-system -o yaml`.

**Q68: Node memory alert fires at 85%. What actions do you take?**
Check which pods are consuming the most memory (`kubectl top pods`). Look for memory leaks (steadily increasing usage). Consider adjusting pod memory limits, adding nodes, or enabling cluster autoscaler if not already active.

---

## Security

**Q69: How does this platform prevent lateral movement after a container is compromised?**
NetworkPolicies restrict pod-to-pod communication to explicit allow rules. Containers run as non-root with read-only filesystems. No shell or package manager in distroless images. Workload Identity limits GCP API access per service account.

**Q70: A secret was accidentally committed to Git. What's your response?**
1) Rotate the secret immediately. 2) Remove from Git history (`git filter-branch` or BFG Repo Cleaner). 3) Force push the cleaned history. 4) Audit access logs for unauthorized use. 5) Add `.gitignore` rules and pre-commit hooks to prevent recurrence.

**Q71: How would you implement pod-level encryption for inter-service traffic?**
Options: Istio/Linkerd service mesh (automatic mTLS between pods), or application-level TLS. Service mesh is transparent to the application and provides certificate rotation, but adds sidecar overhead.

**Q72: Why are distroless images more secure than Alpine?**
Alpine still includes a shell (`/bin/sh`), package manager (`apk`), and OS utilities. An attacker with RCE can install tools, exfiltrate data, or pivot. Distroless has none of this — only the application binary and its runtime dependencies.

**Q73: How does RBAC on the ArgoCD AppProject prevent misdeployment?**
The AppProject restricts: source repos (only this repo), destination namespaces (only the app namespaces), and allowed resource kinds. An Application can't deploy to `kube-system` or create ClusterRoles, even if someone misconfigures it.

---

## Troubleshooting Scenarios

**Q74: Pods are running but the application returns 502 errors. What's happening?**
The load balancer's health check is passing but the app isn't serving correctly. Check: readiness probe config vs. actual app health endpoint, backend service health in GCP console, pod logs for errors, and whether the Ingress backend port matches the Service port.

**Q75: `terraform apply` succeeded but pods can't reach GCP APIs. Diagnosis?**
Likely Private Google Access isn't enabled on the subnet, or the Workload Identity binding is misconfigured. Check: `google_compute_subnetwork` has `private_ip_google_access = true`, GCP SA <-> KSA binding exists, and pods use the correct KSA.

**Q76: ArgoCD sync succeeds but the app is unhealthy. What's the gap?**
Sync only means manifests were applied — it doesn't mean the app is working. Check: pods are actually running (not pending/crashing), readiness probes are configured and passing, ConfigMaps/Secrets are correct, and dependent services are available.

**Q77: After scaling from 2 to 10 replicas, some pods are Pending. Why?**
Cluster doesn't have enough node capacity. The cluster autoscaler needs time to provision new nodes. Check: autoscaler is enabled, node pool max size is sufficient, no resource quotas blocking, and the pod's resource requests can fit on the machine type.

**Q78: A Kustomize overlay produces invalid YAML. How do you catch this before deployment?**
Run `kubectl kustomize k8s/overlays/<env>` locally or in CI to render and validate. Add `kubeval` or `kubeconform` to the CI pipeline for schema validation. ArgoCD also validates manifests during sync and will report errors.

**Q79: Grafana shows no data for a service. Prometheus is running fine.**
Check: service has `prometheus.io/scrape: "true"` annotation, metrics endpoint path/port is correct, Prometheus targets page shows the service (check for scrape errors), and the Grafana query uses the correct metric name and label filters.

**Q80: Image pull fails with "manifest unknown" error.**
The image tag doesn't exist in the registry. Check: CI pipeline actually pushed the tag, the image name in the deployment matches the registry path exactly, and the tag in `kustomization.yaml` matches what was pushed.

**Q81: After a GKE version upgrade, pods fail with API deprecation errors.**
Some Kubernetes API versions are removed in newer releases (e.g., `extensions/v1beta1`). Check deprecation warnings in `kubectl get events`. Update manifests to use current API versions. Run `kubectl convert` or `kubent` to find deprecated APIs before upgrading.

**Q82: Cloud NAT port exhaustion causes intermittent connectivity.**
Each NAT IP supports ~64K connections. High-traffic clusters can exhaust this. Fix: allocate more NAT IPs, enable dynamic port allocation, reduce connection-heavy workloads, or use Private Google Access to bypass NAT for GCP traffic.

**Q83: A node is in `NotReady` state. Impact and resolution?**
Pods on that node will be evicted after the `pod-eviction-timeout` (default 5 min). Kubernetes reschedules them to healthy nodes. Check: kubelet status on the node, disk/memory pressure conditions, network connectivity, and node system logs.

**Q84: Deployment is stuck because of a PDB violation during node drain.**
The PDB's `minAvailable` can't be satisfied if there aren't enough healthy replicas on other nodes. Scale up replicas first, or temporarily relax the PDB. In prod with anti-affinity, ensure enough nodes exist to distribute pods before draining.

---

## Architecture & Design

**Q85: Why three separate microservices instead of a monolith?**
Independent deployment cycles — the frontend (Go) and backends (Python) can be updated, scaled, and debugged independently. Different language runtimes can be optimized per service. Failure isolation prevents one service from taking down the entire platform.

**Q86: Why Go for the frontend and Python for the backends?**
Go produces small, statically compiled binaries — ideal for a lightweight frontend proxy. Python with FastAPI/Flask is productive for CRUD-style backend APIs. This demonstrates polyglot architecture, common in real microservice platforms.

**Q87: How would you add a database to this architecture?**
Options: Cloud SQL (managed Postgres/MySQL) with Private Service Connect for private access, or in-cluster StatefulSet (for dev). Use Terraform to provision Cloud SQL, create a KSA with `cloudsql.client` role via Workload Identity, and deploy Cloud SQL Proxy as a sidecar.

**Q88: How would you add a new environment (e.g., `perf-test`)?**
1) Create `k8s/overlays/perf-test/` with `kustomization.yaml` and patches. 2) Add `argocd/apps/perf-test.yaml` Application manifest. 3) Commit. The app-of-apps pattern auto-discovers it. No ArgoCD reconfiguration needed.

**Q89: What's the upgrade path for GKE control plane and node pools?**
GKE supports sequential minor version upgrades. Upgrade control plane first, then node pools. Use surge upgrades for zero-downtime node pool updates. PDBs protect workloads during node drain. Test in dev/staging before prod.

**Q90: How would you implement rate limiting at the platform level?**
Options: GCP Cloud Armor policies on the HTTP(S) LB (WAF + rate limiting, no app changes), Ingress-level annotations if using nginx-ingress, or application-level middleware. Cloud Armor is the least invasive for this architecture.
