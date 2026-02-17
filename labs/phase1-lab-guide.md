# Phase 1 Lab: Containers & Kubernetes on Minikube

Your platform is already deployed. This guide teaches you to understand, explore, break, and fix it — the skills that matter in interviews.

---

## What's Running Right Now

```
Your Laptop
    |
    | curl http://127.0.0.1:61997
    v
[Minikube VM]
    |
    | NodePort :30088
    v
[frontend pod]  ---- Go service, port 8080
    |       |
    v       v
[order-service]  [product-service]   ---- Python services
  port 8081         port 8082
```

---

## Exercise 1: Explore What Helm Deployed

**WHY:** In interviews, they'll ask "how do you see what's running in a cluster?" These are your daily commands.

```bash
# See the Helm release — Helm tracks everything it deployed as a "release"
helm list -n dev

# See ALL resources Helm created — this shows every K8s object
helm get manifest platform -n dev

# See pods (the actual running containers)
kubectl get pods -n dev

# See services (how pods are exposed to each other)
kubectl get svc -n dev

# See everything in the namespace at once
kubectl get all -n dev
```

**UNDERSTAND THIS:** Each pod has an IP that changes on restart. Services give pods a stable DNS name. That's why the frontend uses `http://order-service:8081` — not a pod IP.

---

## Exercise 2: Understand Pod Details

**WHY:** `kubectl describe` is the #1 debugging tool. Interviewers expect you to know this.

```bash
# Pick any pod name from Exercise 1, then:
kubectl describe pod <pod-name> -n dev
```

**READ THE OUTPUT — look for these sections:**
- **Containers** — image name, ports, environment variables
- **Conditions** — Ready, ContainersReady (both should be True)
- **Events** — the timeline of what happened (Scheduled, Pulled, Created, Started)

```bash
# See resource usage (CPU/memory) of each pod
kubectl top pods -n dev

# See container logs (the application's stdout)
kubectl logs <frontend-pod-name> -n dev

# Follow logs in real-time (Ctrl+C to stop)
kubectl logs -f <order-service-pod-name> -n dev
```

---

## Exercise 3: Test the APIs

**WHY:** You need to verify services communicate correctly. In production, this is health checking.

```bash
# Get the frontend URL
minikube service frontend --url -n dev

# Use that URL for all curl commands below (or use http://127.0.0.1:61997)
URL=http://127.0.0.1:61997

# Health check — is the frontend alive?
curl $URL/healthz

# Status check — can the frontend reach backends?
curl $URL/status

# Get all products (proxied to product-service)
curl $URL/api/products/

# Create an order (proxied to order-service)
curl -X POST $URL/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"product_id":"prod-001","quantity":3}'

# List all orders
curl $URL/api/orders/
```

---

## Exercise 4: Exec Into a Container (Shell Access)

**WHY:** Sometimes you need to debug from inside the container. This is like SSH-ing into a server.

```bash
# The Python containers have a shell (they use python:slim base)
kubectl exec -it <order-service-pod-name> -n dev -- /bin/bash

# Once inside, try:
whoami              # Should be "appuser" (non-root!)
hostname            # The pod name
cat /etc/os-release # Debian (python:slim base)
env                 # See environment variables
ls /app             # The application files
curl localhost:8081/healthz   # Won't work! curl isn't installed
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8081/healthz').read().decode())"
exit

# NOW try the Go frontend (distroless — NO shell!)
kubectl exec -it <frontend-pod-name> -n dev -- /bin/sh
# ERROR! This will fail because distroless has no shell
# This is a SECURITY FEATURE — if an attacker gets RCE, they can't do anything
```

**INTERVIEW POINT:** "Why use distroless?" — No shell, no package manager, no OS utilities. Minimizes attack surface.

---

## Exercise 5: Break Things (Then Fix Them)

**WHY:** The best way to learn Kubernetes is to break it and watch how it responds.

### 5a: Kill a pod (test self-healing)

```bash
# Delete a pod — Kubernetes should recreate it automatically
kubectl delete pod <order-service-pod-name> -n dev

# Watch it come back (Ctrl+C to stop watching)
kubectl get pods -n dev -w

# WHY did it come back? Because the Deployment controller maintains
# the desired replica count. You said 1 replica, so K8s ensures 1 exists.
```

### 5b: Scale up replicas

```bash
# Scale order-service to 3 replicas
kubectl scale deployment order-service --replicas=3 -n dev

# Watch new pods appear
kubectl get pods -n dev -w

# Now scale back to 1
kubectl scale deployment order-service --replicas=1 -n dev

# WHY does this work? The Deployment controller adjusts the ReplicaSet
# to match your desired count. Extra pods get terminated gracefully.
```

### 5c: Deploy a bad image (simulate a failed deployment)

```bash
# Set a non-existent image tag
kubectl set image deployment/frontend frontend=gitops/frontend:doesnotexist -n dev

# Watch the pod fail
kubectl get pods -n dev -w

# You'll see: ImagePullBackOff or ErrImagePull
# The old pod stays running (Rolling Update strategy keeps the old one alive
# until the new one is healthy)

# Diagnose:
kubectl describe pod <new-failing-pod-name> -n dev
# Look at Events — you'll see "Failed to pull image"

# FIX IT — rollback to the previous version
kubectl rollout undo deployment/frontend -n dev

# Verify it's healthy again
kubectl get pods -n dev
curl http://127.0.0.1:61997/status
```

### 5d: Cause an OOMKill (memory limit exceeded)

```bash
# The memory limit is 64Mi. Let's see what happens when it's too low.
# Patch the frontend to have a 1Mi memory limit (impossibly low)
kubectl patch deployment frontend -n dev -p '{"spec":{"template":{"spec":{"containers":[{"name":"frontend","resources":{"limits":{"memory":"1Mi"}}}]}}}}'

# Watch the pod crash
kubectl get pods -n dev -w
# You'll see: OOMKilled in STATUS

# Diagnose:
kubectl describe pod <crashing-pod-name> -n dev
# Look for: "Last State: Terminated, Reason: OOMKilled"

# FIX IT — restore with Helm (resets to values.yaml settings)
helm upgrade platform c:/Learning/Cloud_engineer/helm/gitops-platform/ -n dev
kubectl get pods -n dev -w
```

---

## Exercise 6: Understand Helm Values

**WHY:** Helm's power is changing one values file to configure everything. This is how real teams manage dev/staging/prod.

```bash
# See current values
helm get values platform -n dev

# Upgrade with a different replica count (without editing files)
helm upgrade platform c:/Learning/Cloud_engineer/helm/gitops-platform/ \
  -n dev --set frontend.replicas=2

# Verify 2 frontend pods exist
kubectl get pods -n dev -l app=frontend

# Rollback to previous Helm revision
helm rollback platform 1 -n dev

# See Helm release history
helm history platform -n dev
```

**INTERVIEW POINT:** "How do you manage different environments?"
- `helm install -f values-dev.yaml` for dev
- `helm install -f values-prod.yaml` for prod
- Same chart, different values files.

---

## Exercise 7: DNS and Service Discovery

**WHY:** Understanding Kubernetes DNS is fundamental. Services find each other by name.

```bash
# Start a temporary debug pod with networking tools
kubectl run debug --rm -it --image=busybox -n dev -- /bin/sh

# Inside the debug pod:
nslookup order-service
nslookup product-service
nslookup frontend

# Full DNS name format:
nslookup order-service.dev.svc.cluster.local

# Try calling the services directly:
wget -qO- http://order-service:8081/healthz
wget -qO- http://product-service:8082/api/products
wget -qO- http://frontend:80/status

exit
```

**INTERVIEW POINT:** K8s DNS pattern is `<service>.<namespace>.svc.cluster.local`. Services in the same namespace can use just `<service>`.

---

## Exercise 8: View and Understand Logs

**WHY:** When something breaks in production, logs are your first stop.

```bash
# Logs from a specific pod
kubectl logs <order-service-pod-name> -n dev

# Follow logs in real-time while you make API calls in another terminal
kubectl logs -f <order-service-pod-name> -n dev

# In another terminal, create some orders:
curl -X POST http://127.0.0.1:61997/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"product_id":"prod-002","quantity":5}'

# See all logs from a deployment (all pods)
kubectl logs deployment/order-service -n dev

# See logs from the previous crashed container (after Exercise 5c)
kubectl logs <pod-name> -n dev --previous
```

---

## Exercise 9: Port Forwarding (Debug Individual Services)

**WHY:** Sometimes you need to test a backend service directly, bypassing the frontend.

```bash
# Forward order-service port to your laptop
kubectl port-forward svc/order-service 9081:8081 -n dev

# In another terminal, call it directly:
curl http://localhost:9081/healthz
curl http://localhost:9081/api/orders/

# Ctrl+C to stop port-forward
# This is useful for debugging — "is the backend broken, or is the proxy broken?"
```

---

## Exercise 10: Clean Up and Redeploy

**WHY:** Helm makes teardown and redeployment trivial. This is why teams use it.

```bash
# Delete everything deployed by Helm (one command!)
helm uninstall platform -n dev

# Verify everything is gone
kubectl get all -n dev

# Redeploy from scratch
helm install platform c:/Learning/Cloud_engineer/helm/gitops-platform/ -n dev

# Verify everything is back
kubectl get pods -n dev -w
```

---

## Key Concepts Cheat Sheet

| Concept | What It Does | Command |
|---------|-------------|---------|
| **Pod** | Smallest deployable unit (1+ containers) | `kubectl get pods` |
| **Deployment** | Manages pod replicas, rolling updates | `kubectl get deployments` |
| **Service** | Stable DNS name + load balancing for pods | `kubectl get svc` |
| **Namespace** | Isolation boundary (like a folder) | `kubectl get ns` |
| **NodePort** | Exposes service outside cluster on a port | Check `svc` TYPE column |
| **ClusterIP** | Internal-only service (default) | Check `svc` TYPE column |
| **Helm Release** | A deployed instance of a chart | `helm list` |
| **imagePullPolicy: Never** | Use local Docker images (no registry) | In Helm values |
| **Liveness Probe** | "Is this alive?" — restart if no | In Deployment spec |
| **Readiness Probe** | "Can this handle traffic?" — remove from LB if no | In Deployment spec |

---

## What's Next?

Phase 2 will cover:
- Installing ArgoCD in Minikube
- Pointing ArgoCD at this repo on GitHub
- Making a code change, pushing, and watching ArgoCD auto-sync
- Full GitOps workflow locally — no cloud spend
