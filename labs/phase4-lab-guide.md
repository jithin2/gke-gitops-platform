# Phase 4: Monitoring & Observability

## Why This Phase Matters

In an interview, you'll be asked: "How do you know your application is healthy?"
The wrong answer: "I check the pods."
The right answer: "We have Prometheus collecting metrics, Loki aggregating logs, and Grafana
dashboards with alerts. I can tell you latency, error rate, and saturation at a glance."

This phase teaches you to answer that question with real hands-on experience.

---

## Expert Note: Why NOT ELK Stack

You may have heard of **ELK** (Elasticsearch + Logstash + Kibana). It works, but:
- Elasticsearch needs 4GB+ RAM — it will kill your Minikube
- It's heavyweight, slow to start, complex to configure
- Many companies are migrating away from it

**Modern replacement → Loki** (by Grafana Labs):
- 10x lighter than Elasticsearch
- Stores logs as compressed chunks, not indexed documents
- Same Grafana UI you already use for metrics
- Cheaper in cloud (no expensive Elasticsearch clusters)

**INTERVIEW POINT:** "Why Loki over ELK?" — Loki doesn't index log content, only metadata
(labels like pod name, namespace). This makes it far cheaper and faster to ingest. For full-text
search we use LogQL. For compliance/complex search, ELK still has use cases, but for operational
logs Loki wins on cost and simplicity.

---

## The Three Pillars of Observability

```
┌─────────────────────────────────────────────────────────┐
│                   OBSERVABILITY                         │
│                                                         │
│  METRICS          LOGS              TRACES              │
│  "What is        "What happened     "Where did          │
│  happening?"     and when?"         the time go?"       │
│                                                         │
│  Prometheus      Loki               Tempo/Jaeger        │
│      │               │                   │             │
│      └───────────────┴───────────────────┘             │
│                       │                                 │
│                    Grafana                              │
│              (single pane of glass)                     │
└─────────────────────────────────────────────────────────┘
```

| Pillar | Tool | Answers |
|--------|------|---------|
| **Metrics** | Prometheus | CPU usage, request rate, error rate, latency |
| **Logs** | Loki | What exactly happened, error messages, stack traces |
| **Traces** | Tempo (Phase 5) | Which service caused the slowdown, request path |

---

## What You Will Build

```
Minikube Cluster
│
├── monitoring namespace
│   ├── Prometheus          ← scrapes metrics from all pods
│   ├── Loki                ← collects logs from all pods
│   ├── Promtail            ← agent that ships logs to Loki
│   ├── Grafana             ← dashboards for everything
│   └── Alertmanager        ← sends alerts when things break
│
├── dev namespace
│   ├── frontend            ← your Go service (being monitored)
│   ├── order-service       ← your Python service
│   └── product-service     ← your Python service
```

---

## Module 1: Install the Monitoring Stack

**WHY:** We use the `kube-prometheus-stack` Helm chart — a single chart that installs Prometheus,
Grafana, Alertmanager, and pre-built dashboards. Real teams use this exact chart in production.

### 1.1 — Add the Helm repo

```powershell
# Add Prometheus community Helm charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts

# Add Grafana Helm charts (for Loki)
helm repo add grafana https://grafana.github.io/helm-charts

# Update repos
helm repo update
```

**WHY:** Helm repos are like package managers (apt, npm). We add the source, then install from it.

### 1.2 — Create monitoring namespace

```powershell
kubectl create namespace monitoring
```

**WHY:** Monitoring tools live in their own namespace, separate from your apps.
This follows the principle of separation of concerns — monitoring failure shouldn't affect the app.

### 1.3 — Install kube-prometheus-stack

**WHY:** This single chart installs Prometheus + Grafana + Alertmanager + node exporters +
pre-built Kubernetes dashboards. It's the industry standard starting point.

```powershell
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set prometheus.prometheusSpec.retention=2h \
  --set prometheus.prometheusSpec.resources.requests.memory=256Mi \
  --set prometheus.prometheusSpec.resources.requests.cpu=50m \
  --set grafana.adminPassword=admin123 \
  --set grafana.resources.requests.memory=128Mi \
  --set grafana.resources.requests.cpu=50m \
  --set alertmanager.alertmanagerSpec.resources.requests.memory=64Mi \
  --set nodeExporter.resources.requests.memory=32Mi \
  --set kubeStateMetrics.resources.requests.memory=64Mi
```

**WHY the small resource values:** Minikube has limited RAM. Production would use much higher values.

### 1.4 — Wait for pods to start

```powershell
kubectl get pods -n monitoring -w
```

Wait until all pods show `Running`. This takes 2-3 minutes. Press Ctrl+C when done.

### 1.5 — Install Loki + Promtail (log collection)

**WHY:** Loki stores logs. Promtail is the agent that runs on every node and ships logs to Loki.
Think of Promtail as the "log shipper" and Loki as the "log database".

```powershell
helm install loki grafana/loki-stack \
  --namespace monitoring \
  --set loki.resources.requests.memory=128Mi \
  --set loki.resources.requests.cpu=50m \
  --set promtail.resources.requests.memory=64Mi \
  --set promtail.resources.requests.cpu=25m \
  --set grafana.enabled=false   # we already have Grafana from kube-prometheus-stack
```

### 1.6 — Verify everything is running

```powershell
kubectl get pods -n monitoring
```

You should see:
- `prometheus-prometheus-kube-prometheus-prometheus-0` — the Prometheus server
- `prometheus-grafana-xxx` — Grafana
- `prometheus-kube-prometheus-alertmanager-0` — Alertmanager
- `prometheus-kube-state-metrics-xxx` — cluster state metrics
- `loki-0` — log storage
- `loki-promtail-xxx` — log shipping agent (one per node)

---

## Module 2: Grafana — Your Monitoring Dashboard

### 2.1 — Access Grafana

```powershell
# Port-forward Grafana to your browser
kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80
```

Open `http://localhost:3000`
- Username: `admin`
- Password: `admin123`

**WHY port-forward:** Same as ArgoCD — Grafana's service is ClusterIP (internal only).
Port-forward creates a tunnel from your laptop to the cluster.

### 2.2 — Explore pre-built dashboards

Click **Dashboards** (left sidebar) → **Browse** → you'll see dashboards already installed:

- **Kubernetes / Compute Resources / Cluster** — overall cluster CPU/RAM
- **Kubernetes / Compute Resources / Namespace** — per namespace usage
- **Kubernetes / Compute Resources / Pod** — per pod CPU/RAM
- **Node Exporter / Nodes** — underlying VM metrics

**Exercise:** Open "Kubernetes / Compute Resources / Namespace" → select `dev` namespace
→ you can see your frontend, order-service, product-service resource usage.

**INTERVIEW POINT:** "What dashboards do you monitor?" — Kubernetes compute resource
dashboards for capacity planning, custom application dashboards for business metrics (request
rate, error rate, latency), and node dashboards for infrastructure health.

### 2.3 — Add Loki as a data source

**WHY:** Grafana needs to know where Loki is before it can show logs.

1. Go to **Connections** → **Data Sources** → **Add data source**
2. Search for **Loki** → click it
3. URL: `http://loki:3100`
4. Click **Save & Test** → should show "Data source connected and labels found"

Now Grafana can query both Prometheus (metrics) AND Loki (logs) from one interface.

### 2.4 — View your application logs in Grafana

1. Click **Explore** (compass icon, left sidebar)
2. At the top, switch data source from `Prometheus` to `Loki`
3. Click **Label filters** → add `namespace = dev`
4. Click **Run query**

You'll see all logs from your dev namespace — frontend, order-service, product-service — in one place.

**Filter by service:**
- Add label filter: `app = frontend`
- Now only frontend logs appear

**Search log content (LogQL):**
```
{namespace="dev", app="order-service"} |= "error"
```
This finds all logs from order-service containing the word "error".

**INTERVIEW POINT:** "How do you find errors in logs?" — We use Loki with LogQL. Query by
namespace and app labels, then filter log content. Labels make queries fast (no full-text index
scanning like ELK).

---

## Module 3: Prometheus — Understanding Metrics

### 3.1 — Access Prometheus UI

```powershell
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090
```

Open `http://localhost:9090`

### 3.2 — How Prometheus works

```
Your pods expose metrics at /metrics endpoint
        │
        ▼
Prometheus "scrapes" (reads) /metrics every 15 seconds
        │
        ▼
Stores as time-series data: metric_name{labels} value timestamp
        │
        ▼
Grafana queries Prometheus using PromQL
```

### 3.3 — What does /metrics look like?

Prometheus uses a simple text format. If your app had a `/metrics` endpoint, it would return:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",status="200"} 1234
http_requests_total{method="POST",status="201"} 567
http_requests_total{method="GET",status="500"} 3

# HELP process_cpu_seconds_total CPU usage
process_cpu_seconds_total 0.23
```

Kubernetes components (kubelet, API server) already expose these. Your own apps need a
metrics library to expose them (covered later).

### 3.4 — PromQL basics

**WHY:** PromQL is the query language for Prometheus. You need this for dashboards and alerts.

Open Prometheus UI (`http://localhost:9090`) → click **Graph** tab → try these queries:

**CPU usage by pod:**
```promql
sum(rate(container_cpu_usage_seconds_total{namespace="dev"}[5m])) by (pod)
```
- `rate(...[5m])` — rate of change over 5 minutes
- `sum(...) by (pod)` — group results by pod name

**Memory usage by pod:**
```promql
container_memory_working_set_bytes{namespace="dev"}
```

**Pod restarts (indicates crashes):**
```promql
kube_pod_container_status_restarts_total{namespace="dev"}
```

**Are your pods ready?**
```promql
kube_pod_status_ready{namespace="dev", condition="true"}
```
Returns 1 if ready, 0 if not. Perfect for alerts.

### 3.5 — The four golden signals (industry standard)

Every system should be monitored for these four things:

| Signal | What it is | PromQL example |
|--------|-----------|----------------|
| **Latency** | How long requests take | `histogram_quantile(0.99, rate(http_duration_seconds_bucket[5m]))` |
| **Traffic** | How many requests/sec | `rate(http_requests_total[5m])` |
| **Errors** | % of failed requests | `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])` |
| **Saturation** | How "full" the system is | `container_memory_working_set_bytes / container_spec_memory_limit_bytes` |

**INTERVIEW POINT:** "What do you monitor?" — The four golden signals: Latency, Traffic,
Errors, and Saturation. These come from Google's SRE book and cover what matters most
for user-facing services.

---

## Module 4: Add Metrics to Your Services

**WHY:** Right now Prometheus can only see Kubernetes-level metrics (CPU, RAM, restarts).
It can't see application-level metrics like "how many orders were created?" or "what's the
API error rate?". We need to add metrics to our services.

### 4.1 — Add Prometheus metrics to the Go frontend

Edit `services/frontend/main.go`:

```go
import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promhttp"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

// Define metrics (add these as package-level variables)
var (
    requestsTotal = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "frontend_requests_total",
            Help: "Total number of HTTP requests",
        },
        []string{"method", "path", "status"},
    )

    requestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "frontend_request_duration_seconds",
            Help:    "HTTP request duration in seconds",
            Buckets: prometheus.DefBuckets,
        },
        []string{"method", "path"},
    )
)

// In main(), add the metrics endpoint:
http.Handle("/metrics", promhttp.Handler())

// Wrap your handlers to record metrics:
http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
    start := time.Now()
    // ... your existing handler logic ...
    duration := time.Since(start).Seconds()

    requestsTotal.WithLabelValues(r.Method, r.URL.Path, "200").Inc()
    requestDuration.WithLabelValues(r.Method, r.URL.Path).Observe(duration)
})
```

Update `services/frontend/go.mod` to add the dependency:
```powershell
cd services/frontend
go get github.com/prometheus/client_golang/prometheus
go get github.com/prometheus/client_golang/prometheus/promhttp
go get github.com/prometheus/client_golang/prometheus/promauto
```

### 4.2 — Tell Prometheus to scrape your services

**WHY:** Prometheus doesn't automatically scrape your custom pods. You need a `ServiceMonitor`
resource — a Prometheus-specific Kubernetes resource that says "please scrape this service."

Create `k8s/base/monitoring/servicemonitor.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: platform-services
  namespace: monitoring
  labels:
    release: prometheus    # must match the Helm release name
spec:
  namespaceSelector:
    matchNames:
      - dev
  selector:
    matchLabels:
      tier: web            # matches frontend pod label
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

```powershell
kubectl apply -f k8s/base/monitoring/servicemonitor.yaml
```

### 4.3 — Verify Prometheus is scraping your service

1. Go to Prometheus UI → **Status** → **Targets**
2. Look for your frontend service — it should show `UP`
3. In the Graph tab, query: `frontend_requests_total`

Make a few requests to your frontend:
```powershell
curl http://$(minikube ip):30088/
curl http://$(minikube ip):30088/api/products
curl http://$(minikube ip):30088/api/orders
```

Then query in Prometheus:
```promql
rate(frontend_requests_total[1m])
```

You should see request rates per path.

---

## Module 5: Grafana Dashboards

### 5.1 — Build your first dashboard

**WHY:** Pre-built dashboards show Kubernetes metrics. We need a custom dashboard for
our application business metrics.

1. In Grafana → click **+** → **New Dashboard** → **Add visualization**
2. Select data source: **Prometheus**

**Panel 1: Request Rate**
- Query: `sum(rate(frontend_requests_total[5m])) by (path)`
- Visualization: **Time series**
- Title: "Requests per second by path"

**Panel 2: Error Rate**
- Query: `sum(rate(frontend_requests_total{status=~"5.."}[5m])) / sum(rate(frontend_requests_total[5m]))`
- Visualization: **Stat** (single number)
- Title: "Error Rate %"
- Set thresholds: green < 1%, yellow < 5%, red > 5%

**Panel 3: p99 Latency**
- Query: `histogram_quantile(0.99, rate(frontend_request_duration_seconds_bucket[5m]))`
- Visualization: **Time series**
- Title: "p99 latency (seconds)"

**Panel 4: Pod Status**
- Query: `kube_pod_status_ready{namespace="dev", condition="true"}`
- Visualization: **Stat**
- Title: "Pods Ready"

**Panel 5: Memory Usage**
- Query: `container_memory_working_set_bytes{namespace="dev"}`
- Visualization: **Time series**
- Title: "Memory usage by pod"

Save the dashboard as "Platform Overview".

### 5.2 — Logs panel in Grafana

**WHY:** Seeing logs alongside metrics in one dashboard = faster debugging.

Add a new panel:
- Data source: **Loki**
- Query: `{namespace="dev"} |= "error"`
- Visualization: **Logs**
- Title: "Recent errors"

Now your dashboard shows metrics AND logs together. When the error rate spikes, you can see
the exact error messages without switching tools.

**INTERVIEW POINT:** "How do you correlate metrics with logs?" — In Grafana, we can have
Prometheus metrics and Loki logs on the same dashboard. When an alert fires, the dashboard
shows both the spike in error rate AND the log messages causing it. No need to switch between
tools.

### 5.3 — Export your dashboard as JSON

**WHY:** Dashboards should be in version control, not just in Grafana's database.
If Grafana restarts, you lose your dashboards without this.

1. Open your dashboard
2. Click the **Share** icon → **Export** → **Export for sharing externally**
3. Copy the JSON
4. Save to `monitoring/grafana-dashboards/platform-overview.json`

```powershell
git add monitoring/grafana-dashboards/platform-overview.json
git commit -m "Add platform overview Grafana dashboard"
git push
```

**INTERVIEW POINT:** "How do you manage Grafana dashboards?" — Dashboards are stored as
JSON in Git. This means they're version-controlled, reviewable in PRs, and can be automatically
loaded via Grafana provisioning on startup.

---

## Module 6: Alerting

**WHY:** You can't stare at dashboards 24/7. Alerts notify you when something breaks.

### 6.1 — How alerting works

```
Prometheus evaluates alert rules every 15 seconds
        │
        ▼
If condition is true for X minutes → alert fires
        │
        ▼
Alertmanager receives the alert
        │
        ▼
Alertmanager routes it → email / Slack / PagerDuty
```

### 6.2 — Create alert rules

Create `monitoring/alerting-rules.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: platform-alerts
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: platform.rules
      interval: 30s
      rules:

        # Alert if a pod is not ready for more than 2 minutes
        - alert: PodNotReady
          expr: kube_pod_status_ready{namespace="dev", condition="true"} == 0
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Pod {{ $labels.pod }} is not ready"
            description: "Pod {{ $labels.pod }} in namespace {{ $labels.namespace }} has been not ready for 2 minutes."

        # Alert if pod is restarting frequently
        - alert: PodCrashLooping
          expr: rate(kube_pod_container_status_restarts_total{namespace="dev"}[15m]) > 0
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} is crash looping"
            description: "Pod {{ $labels.pod }} has restarted more than once in 15 minutes."

        # Alert if memory usage is above 80% of limit
        - alert: HighMemoryUsage
          expr: |
            container_memory_working_set_bytes{namespace="dev"}
            /
            container_spec_memory_limit_bytes{namespace="dev"}
            > 0.8
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High memory usage in {{ $labels.pod }}"
            description: "{{ $labels.pod }} is using more than 80% of its memory limit."

        # Alert if error rate exceeds 5%
        - alert: HighErrorRate
          expr: |
            sum(rate(frontend_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(frontend_requests_total[5m]))
            > 0.05
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "High error rate on frontend"
            description: "Frontend error rate is above 5% for the last 2 minutes."
```

```powershell
kubectl apply -f monitoring/alerting-rules.yaml
```

### 6.3 — Verify alerts in Prometheus

1. Go to `http://localhost:9090` → **Alerts** tab
2. You should see your alert rules listed
3. Status: `inactive` (good — no problems currently)

**Trigger a PodNotReady alert intentionally:**
```powershell
# Scale frontend to 0 — all pods gone
kubectl scale deployment frontend --replicas=0 -n dev

# Wait 2 minutes, then check Prometheus Alerts tab
# PodNotReady alert should go from inactive → pending → firing

# Restore
kubectl scale deployment frontend --replicas=2 -n dev
```

**INTERVIEW POINT:** "How do you set up alerts?" — PrometheusRule resources define alert
conditions in PromQL. Each alert has a `for` duration (must be true for X minutes before firing,
prevents flapping), labels for routing (severity: critical vs warning), and annotations with
human-readable descriptions. Alertmanager then routes based on severity.

### 6.4 — View alerts in Alertmanager

```powershell
kubectl port-forward svc/prometheus-kube-prometheus-alertmanager -n monitoring 9093:9093
```

Open `http://localhost:9093` — you'll see active alerts and silences.

**Silences:** If you're doing maintenance and don't want alert noise, you create a silence:
"Silence all alerts for the `dev` namespace for the next 2 hours."

---

## Module 7: SLOs and SLIs (Industry Concepts)

**WHY:** These terms come up constantly in senior DevOps/SRE interviews.

### 7.1 — Definitions

| Term | Meaning | Example |
|------|---------|---------|
| **SLI** (Service Level Indicator) | A metric you measure | Error rate = 0.2% |
| **SLO** (Service Level Objective) | Your target for the SLI | Error rate < 1% |
| **SLA** (Service Level Agreement) | Legal contract with customers | 99.9% uptime or we pay you |
| **Error Budget** | How much you can fail within SLO | 0.1% errors/month = 43 minutes downtime |

### 7.2 — Common SLIs and SLOs

| Service | SLI | SLO |
|---------|-----|-----|
| Frontend API | p99 latency | < 500ms |
| Frontend API | Error rate | < 0.1% |
| Frontend API | Availability | > 99.9% |
| Order service | Order creation time | < 2s p95 |

### 7.3 — Error budget in practice

If your SLO is 99.9% uptime per month:
- Total minutes in a month: 43,200
- 0.1% downtime allowed: **43 minutes**

If you've used 40 minutes of downtime this month, you have 3 minutes left.
This means: **no risky deployments until next month.**

Error budgets create a shared language between developers and ops:
- "We have budget left" → safe to deploy new features
- "Budget nearly exhausted" → freeze deployments, focus on reliability

**INTERVIEW POINT:** "What is an error budget?" — The amount of downtime/errors we're
allowed before violating our SLO. It's calculated as (1 - SLO) × time period. When the budget
is spent, we stop deploying new features and focus on reliability. This creates alignment between
dev speed and system reliability.

### 7.4 — Add SLO-based alert (burn rate alert)

Instead of alerting "error rate > 5% for 2 minutes" (too slow), burn rate alerts ask:
"Are we consuming error budget fast enough to exhaust it in X hours?"

```yaml
# In monitoring/alerting-rules.yaml, add:
- alert: ErrorBudgetBurnRateHigh
  expr: |
    sum(rate(frontend_requests_total{status=~"5.."}[1h]))
    /
    sum(rate(frontend_requests_total[1h]))
    > 0.001   # if burning > 1% errors in last hour
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "High error budget burn rate"
    description: "At current rate, monthly error budget will be exhausted in < 4 hours."
```

---

## Module 8: Monitoring as Code

**WHY:** All your monitoring config should live in Git — dashboards, alerts, Prometheus rules.
If your cluster dies, you should be able to recreate everything from code.

### 8.1 — Current state of your monitoring-as-code

```
monitoring/
├── alerting-rules.yaml           ← PrometheusRule (already in Git)
├── prometheus-values.yaml        ← Helm values for kube-prometheus-stack
├── loki-values.yaml              ← Helm values for Loki
└── grafana-dashboards/
    └── platform-overview.json    ← exported Grafana dashboard JSON
```

### 8.2 — Add monitoring to ArgoCD

**WHY:** Just like your app manifests, monitoring config should be deployed by ArgoCD.
This means your dashboards and alerts are automatically applied when the cluster is recreated.

Create `argocd/applications/monitoring.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: monitoring
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/jithin2/gke-gitops-platform.git
    targetRevision: main
    path: monitoring
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

Now when you change `alerting-rules.yaml` and push to Git, ArgoCD applies the new rules
automatically — same GitOps pattern as your app deployments.

---

## Module 9: Observability Best Practices (Interview Ready)

### Structured logging

**WHY:** Logs like `"Error: connection failed"` are hard to query. JSON logs are queryable.

Your Python services should log like this:

```python
import json
import logging

# Instead of:
print(f"Error processing order {order_id}")

# Do this:
logging.info(json.dumps({
    "level": "error",
    "message": "Error processing order",
    "order_id": order_id,
    "service": "order-service",
    "trace_id": "abc123"
}))
```

In Loki, you can then query:
```
{app="order-service"} | json | order_id = "12345"
```

### USE Method (for resources)

For every resource (CPU, memory, disk, network):
- **U**tilization — how busy is it? (e.g., 70% CPU)
- **S**aturation — how much is it waiting? (e.g., 100 requests queued)
- **E**rrors — error rate (e.g., disk write errors)

### RED Method (for services)

For every service:
- **R**ate — requests per second
- **E**rrors — error rate
- **D**uration — latency (p50, p95, p99)

---

## What You Can Now Answer in Interviews

| Question | Your Answer |
|----------|-------------|
| "How do you monitor your services?" | Prometheus for metrics, Loki for logs, Grafana for dashboards — the PLG stack |
| "Why not ELK?" | Loki is 10x lighter, cheaper, native Grafana integration. ELK suits compliance/full-text search |
| "What are the four golden signals?" | Latency, Traffic, Errors, Saturation |
| "What is an SLO?" | Target for an SLI — e.g., p99 latency < 500ms. Violation costs error budget |
| "How do you alert on issues?" | PrometheusRule resources, evaluated by Prometheus, routed by Alertmanager |
| "How do you prevent alert fatigue?" | Burn rate alerts, severity levels, Alertmanager grouping and silences |
| "How do you store dashboards?" | JSON in Git, version controlled, auto-loaded via Grafana provisioning |
| "How do you correlate logs and metrics?" | Grafana shows both on same dashboard, Loki and Prometheus as data sources |
| "What is structured logging?" | JSON-formatted logs with consistent fields, queryable with LogQL |
| "What is an error budget?" | (1 - SLO) × time. Spent budget = stop deploying, focus on reliability |

---

## What's Next — Phase 5

- **Distributed Tracing** with Tempo (Grafana's tracing tool)
- Understanding spans, traces, and context propagation
- Instrumenting Go and Python services with OpenTelemetry
- Seeing request flow across frontend → order-service → product-service in one trace
- Connecting traces to logs (trace ID in log lines)
