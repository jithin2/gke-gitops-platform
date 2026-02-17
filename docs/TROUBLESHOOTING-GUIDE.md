# Production Troubleshooting Runbook

This is a real-world troubleshooting guide organized by symptom. Each section follows the pattern: **Symptom → Diagnosis → Root Cause → Fix → Prevention**.

---

## Table of Contents
- [Pod Issues](#pod-issues)
- [Service/Networking Issues](#servicenetworking-issues)
- [Storage Issues](#storage-issues)
- [GKE/GCP Issues](#gkegcp-issues)
- [ArgoCD Issues](#argocd-issues)
- [Performance Issues](#performance-issues)

---

## Pod Issues

### CrashLoopBackOff

**Symptom:** Pod repeatedly starts and crashes, backoff timer increases.

**Diagnosis:**
```bash
# Check pod events
kubectl describe pod <pod-name> -n <namespace>

# Check container logs (current crash)
kubectl logs <pod-name> -n <namespace>

# Check previous crash logs
kubectl logs <pod-name> -n <namespace> --previous

# Check exit code
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'
```

**Common Root Causes:**
| Exit Code | Meaning | Typical Cause |
|-----------|---------|---------------|
| 0 | Success | App exiting normally (misconfigured CMD) |
| 1 | General error | App error, missing config/env var |
| 137 | SIGKILL (128+9) | OOMKilled or external kill |
| 139 | SIGSEGV (128+11) | Segmentation fault |
| 143 | SIGTERM (128+15) | Graceful shutdown timeout exceeded |

**Fix by exit code:**
- **Exit 1:** Check logs for application errors. Verify environment variables and ConfigMaps are mounted correctly.
- **Exit 137 (OOMKilled):** Increase memory limits. Check `kubectl describe pod` for `OOMKilled` reason.
- **Exit 143:** Increase `terminationGracePeriodSeconds`. Ensure app handles SIGTERM.

**Prevention:**
- Set proper resource limits
- Add startup probes for slow-starting containers
- Test container locally: `docker run --rm <image>`

---

### ImagePullBackOff

**Symptom:** Pod stuck in `ImagePullBackOff` or `ErrImagePull`.

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A5 "Events"
# Look for: "Failed to pull image" messages
```

**Common Root Causes:**
1. **Wrong image name/tag:** Typo in image reference
2. **Registry auth failure:** Missing or expired `imagePullSecrets`
3. **Private registry:** GKE nodes can't reach Artifact Registry
4. **Image doesn't exist:** Tag was never pushed

**Fix:**
```bash
# Verify image exists
gcloud artifacts docker images list us-central1-docker.pkg.dev/PROJECT_ID/gitops-platform-images

# Check if nodes have Artifact Registry access
# Node SA needs roles/artifactregistry.reader

# For imagePullSecrets issues:
kubectl create secret docker-registry regcred \
  --docker-server=us-central1-docker.pkg.dev \
  --docker-username=_json_key \
  --docker-password="$(cat key.json)"
```

**Prevention:**
- Use Workload Identity instead of key-based auth
- Pin image tags (never use `latest` in production)
- CI pipeline should verify image push succeeded before updating manifests

---

### Pod Stuck in Pending

**Symptom:** Pod stays in `Pending` state indefinitely.

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
# Look for Events section — the scheduler tells you exactly why

kubectl get events -n <namespace> --sort-by='.lastTimestamp' | grep <pod-name>
```

**Common Root Causes:**

| Event Message | Cause | Fix |
|---------------|-------|-----|
| `Insufficient cpu/memory` | Node resources exhausted | Scale up node pool or reduce requests |
| `0/3 nodes are available: 3 node(s) had taint` | Taint/toleration mismatch | Add toleration or remove taint |
| `no persistent volumes available` | PVC not bound | Check StorageClass and provisioner |
| `0/3 nodes are available: 3 didn't match Pod's node affinity` | Node selector/affinity | Fix labels or affinity rules |
| `pod has unbound immediate PersistentVolumeClaims` | PVC pending | Debug PVC separately |

**Fix for resource exhaustion:**
```bash
# Check node allocatable vs requested
kubectl describe nodes | grep -A5 "Allocated resources"

# Check cluster autoscaler status
kubectl -n kube-system describe cm cluster-autoscaler-status

# Manually scale if autoscaler isn't responding
gcloud container clusters resize gitops-platform --node-pool general --num-nodes 3 --region us-central1
```

---

### OOMKilled

**Symptom:** Container terminated with reason `OOMKilled`, exit code 137.

**Diagnosis:**
```bash
# Confirm OOM
kubectl describe pod <pod-name> | grep -A3 "Last State"
# Output: Reason: OOMKilled

# Check current memory usage
kubectl top pod <pod-name> -n <namespace>

# Check memory limit
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].resources.limits.memory}'
```

**Fix:**
```bash
# Option 1: Increase memory limit (in Kustomize overlay)
# k8s/overlays/prod/patches/resources.yaml
resources:
  limits:
    memory: 512Mi  # Was 256Mi

# Option 2: Fix the memory leak in application code
# Profile memory usage locally first
```

**Key Insight:** `requests` vs `limits`:
- **requests** = guaranteed minimum (used for scheduling)
- **limits** = maximum allowed (OOMKilled if exceeded)
- Set `requests` close to actual usage, `limits` with headroom for spikes

---

## Service/Networking Issues

### Service Not Routing Traffic

**Symptom:** Requests to Service get connection refused or timeout.

**Diagnosis:**
```bash
# Step 1: Check endpoints exist
kubectl get endpoints <service-name> -n <namespace>
# If ENDPOINTS is <none>, selectors don't match any pods

# Step 2: Verify selector matches pod labels
kubectl get svc <service-name> -o jsonpath='{.spec.selector}'
kubectl get pods -l app=<service-name> -n <namespace>

# Step 3: Check if pods are Ready
kubectl get pods -l app=<service-name> -n <namespace>
# Pods must be Running AND Ready (1/1)

# Step 4: Test from within cluster
kubectl run debug --image=busybox --rm -it -- wget -qO- http://<service-name>:<port>/healthz
```

**Common Root Causes:**
1. Selector mismatch between Service and Deployment labels
2. Pods not passing readiness probe → removed from endpoints
3. Wrong `targetPort` in Service spec
4. NetworkPolicy blocking traffic

---

### DNS Resolution Failures

**Symptom:** `nslookup` or `curl` fails with "could not resolve host" from inside pods.

**Diagnosis:**
```bash
# Test DNS from a debug pod
kubectl run dns-test --image=busybox --rm -it -- nslookup kubernetes.default
kubectl run dns-test --image=busybox --rm -it -- nslookup order-service.default.svc.cluster.local

# Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns
```

**Common Root Causes:**
1. CoreDNS pods are crashing or overloaded
2. NetworkPolicy blocking DNS (UDP port 53)
3. `ndots` setting causing excessive DNS queries (default is 5)

**Fix for ndots issue:**
```yaml
# In pod spec — reduces unnecessary DNS lookups
spec:
  dnsConfig:
    options:
      - name: ndots
        value: "2"
```

---

### Network Policy Blocking Traffic

**Symptom:** Pods can't communicate even though Service exists.

**Diagnosis:**
```bash
# List all NetworkPolicies in namespace
kubectl get networkpolicy -n <namespace>

# Check if a default-deny policy exists
kubectl get networkpolicy default-deny-all -n <namespace> -o yaml

# Test connectivity
kubectl exec -it <pod> -- curl -v http://order-service:8081/healthz
```

**Fix:** Ensure your allow policies cover DNS egress and inter-service communication. Our project includes `allow-dns` policy for this reason.

---

## GKE/GCP Issues

### Workload Identity 403 Forbidden

**Symptom:** Application gets `403 Forbidden` when calling GCP APIs (GCS, Pub/Sub, etc).

**Diagnosis:**
```bash
# Step 1: Check K8s ServiceAccount annotation
kubectl get sa order-service -o yaml
# Must have: iam.gke.io/gcp-service-account: order-service@PROJECT.iam.gserviceaccount.com

# Step 2: Check GCP IAM binding
gcloud iam service-accounts get-iam-policy order-service@PROJECT.iam.gserviceaccount.com
# Must have workloadIdentityUser binding for the K8s SA

# Step 3: Verify from inside the pod
kubectl exec -it <pod> -- curl -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email
# Should return the GCP SA email, not the default compute SA
```

**Common Root Causes:**
1. Missing `iam.gke.io/gcp-service-account` annotation on K8s SA
2. Missing `roles/iam.workloadIdentityUser` IAM binding
3. Workload Identity not enabled on node pool (`GKE_METADATA` mode)
4. Pod not using the correct K8s ServiceAccount

---

### Cloud NAT IP Exhaustion

**Symptom:** Outbound connections from pods failing intermittently. `connect: connection timed out`.

**Diagnosis:**
```bash
# Check NAT gateway logs
gcloud logging read 'resource.type="nat_gateway" AND jsonPayload.allocation_status="DROPPED"' --limit=50

# Check allocated ports
gcloud compute routers nats describe gitops-platform-nat --router=gitops-platform-router --region=us-central1
```

**Fix:**
```bash
# Increase minimum ports per VM
gcloud compute routers nats update gitops-platform-nat \
  --router=gitops-platform-router \
  --region=us-central1 \
  --min-ports-per-vm=4096

# Or allocate static IPs for more NAT capacity
```

---

### GKE Node Auto-Upgrade Disruptions

**Symptom:** Pods restarting during maintenance window.

**Prevention:**
```hcl
# Terraform — set maintenance window
maintenance_policy {
  recurring_window {
    start_time = "2024-01-01T02:00:00Z"
    end_time   = "2024-01-01T06:00:00Z"
    recurrence = "FREQ=WEEKLY;BYDAY=TU,WE,TH"
  }
}
```

**Mitigation:**
- Use PodDisruptionBudgets (PDBs) to prevent all pods from being evicted
- Use `topologySpreadConstraints` to spread across zones
- Set `maxUnavailable: 0` in rolling update strategy

---

## ArgoCD Issues

### Application Stuck in "Progressing"

**Symptom:** ArgoCD sync started but never completes.

**Diagnosis:**
```bash
# Check ArgoCD app status
argocd app get <app-name>

# Check for failed resources
argocd app resources <app-name> | grep -v Healthy

# Common: Deployment stuck waiting for rollout
kubectl rollout status deployment/<name> -n <namespace>
```

**Common Root Causes:**
1. New pods failing readiness probes → rollout never completes
2. Insufficient cluster resources → pods Pending
3. HPA conflict — ArgoCD sets replicas, HPA overrides, ArgoCD detects drift

**Fix for HPA conflict:**
```yaml
# In ArgoCD Application spec
ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
      - /spec/replicas
```

---

### Application Shows OutOfSync After Sync

**Symptom:** ArgoCD says OutOfSync immediately after a successful sync.

**Diagnosis:**
```bash
# Check what ArgoCD thinks is different
argocd app diff <app-name>
```

**Common Root Causes:**
1. Mutating webhooks modifying resources after apply (e.g., Istio sidecar injection)
2. Server-side defaulting adding fields not in your manifests
3. HPA changing replica count
4. Kubernetes normalizing fields (e.g., resource quantities `1000m` → `1`)

**Fix:** Use `ignoreDifferences` in the Application spec for expected drift.

---

## Performance Issues

### CPU Throttling with Low CPU Usage

**Symptom:** `kubectl top pod` shows 50% CPU but application is slow.

**Explanation:** CFS (Completely Fair Scheduler) throttling can happen even at low average CPU when there are **burst spikes** that hit the limit within a CFS period (100ms).

**Diagnosis:**
```bash
# Check throttling metrics
kubectl exec -it <pod> -- cat /sys/fs/cgroup/cpu/cpu.stat
# Look for: nr_throttled and throttled_time

# Or via Prometheus
container_cpu_cfs_throttled_periods_total / container_cpu_cfs_periods_total
```

**Fix options:**
1. Increase CPU limit (or remove it — controversial but effective)
2. Optimize hot paths in application code
3. Use `resources.requests` for scheduling, rely on node-level limits

---

### HPA Not Scaling

**Symptom:** HPA shows `<unknown>` for metrics or doesn't scale.

**Diagnosis:**
```bash
# Check HPA status
kubectl get hpa -n <namespace>
# If TARGETS shows <unknown>/70% — metrics not available

# Check metrics-server
kubectl top pods -n <namespace>
# If this fails, metrics-server isn't working

# Check metrics-server pods
kubectl get pods -n kube-system | grep metrics-server

# For GKE Managed Prometheus custom metrics
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1
```

**Common Root Causes:**
1. metrics-server not installed or crashing
2. Pod doesn't have resource `requests` set (required for CPU-based HPA)
3. Custom metrics adapter not configured
4. RBAC preventing HPA from reading metrics
