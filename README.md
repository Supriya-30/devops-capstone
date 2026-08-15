# DevOps Capstone v2: GitOps CI/CD Pipeline

A production-style, **pull-based (GitOps)** delivery pipeline you can build, run, break, and explain in interviews:

**Flask API → Docker → GitHub Actions (test + Trivy scan) → Docker Hub → Git tag bump → ArgoCD → Kubernetes (EKS or minikube) → Prometheus + Grafana**, with **Terraform** provisioning the AWS infrastructure.

> **v1 → v2 (say this in interviews):** v1 deployed by running `helm upgrade` from CI with a kubeconfig stored as a GitHub secret — cluster-admin credentials living in an external system, no drift detection, and "what's running" could differ from "what's in Git". v2 is GitOps: CI only builds, scans, and pushes the image, then **commits the new tag to Git**. ArgoCD runs *inside* the cluster, watches the repo, and syncs it. Git is the single source of truth; `git revert` is the rollback button; `selfHeal` reverts manual drift.

---

## Architecture

```
 Developer pushes code to GitHub (main branch)
        │
        ▼
 GitHub Actions (CI only — no cluster credentials!)
 ├── Stage 1: flake8 + pytest              ← quality gate #1
 ├── Stage 2: Docker build + Trivy scan    ← quality gate #2 (DevSecOps)
 ├── Stage 3: Push image (tag = git SHA)   ← immutable, traceable artifact
 └── Stage 4: Commit new tag to helm/flask-app/values.yaml
        │
        ▼  (pull, not push)
 ArgoCD (in-cluster) watches the repo
 ├── Detects the tag-bump commit
 ├── helm-renders the chart and syncs      ← rolling deployment, zero downtime
 └── selfHeal + prune = drift detection
        │
        ▼
 Kubernetes Cluster (EKS via Terraform, or minikube locally)
 ├── Deployment (hardened: non-root, read-only FS, no caps, seccomp)
 ├── Service (named port) [+ optional Ingress]
 └── HPA (autoscale 2→5 pods at 70% CPU)
        │
        ▼
 Prometheus scrapes /metrics (prometheus_client, multiprocess-safe)
 └── via ServiceMonitor (kube-prometheus-stack) or annotations (compose stack)
        │
        ▼
 Grafana dashboards (RED method: rate, errors, duration)
```

## Repo layout

```
app/                      Flask app + gunicorn config + pytest tests
Dockerfile                Multi-stage, non-root, healthcheck, multiproc metrics dir
docker-compose.yml        Local stack: app + Prometheus + Grafana
monitoring/prometheus.yml Scrape config (annotation/static style, for compose)
.github/workflows/        CI pipeline (test → scan → push → Git tag bump)
helm/flask-app/           Helm chart (+ ingress, ServiceMonitor, per-env values)
argocd/application.yaml   The ArgoCD Application that deploys this repo
terraform/                VPC + EKS via official modules
```

---

## Build it in 6 phases (do them in order)

### Phase 1 — Run locally (Day 1)
```bash
cd app && pip install -r requirements.txt -r requirements-dev.txt
python app.py                  # http://localhost:5000 , /health , /metrics
pytest -v                      # the same tests the pipeline runs
```

### Phase 2 — Containerize (Day 1–2)
```bash
docker build -t devops-capstone:2.0 .
docker run -d -p 5000:5000 --name capstone devops-capstone:2.0
docker logs capstone           # troubleshooting habit: always check logs first
docker compose up --build      # full local stack with Prometheus + Grafana
```
Open Prometheus (localhost:9090) → Status → Targets → confirm the app is UP.
In Grafana (localhost:3000, admin/admin), add Prometheus as a data source (http://prometheus:9090) and graph:
```
sum(rate(app_requests_total[1m])) by (endpoint, status)
histogram_quantile(0.95, sum(rate(app_request_latency_seconds_bucket[5m])) by (le, endpoint))
```

### Phase 3 — CI (Day 3–4)
1. Push this repo to GitHub.
2. Add secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`; set Actions → Workflow permissions → **Read and write** (Stage 4 commits the tag bump).
3. Push a commit → watch: tests → Trivy → image push → a bot commit updating `values.yaml`.
4. Deliberately break a test and push → the release is blocked. **Quality gates as code.**

### Phase 4 — Kubernetes with Helm, manually first (Day 5–6)
Learn what ArgoCD will automate before automating it:
```bash
minikube start
minikube addons enable metrics-server    # or HPA shows <unknown> CPU
minikube addons enable ingress           # if you enable the ingress in values-dev
helm upgrade --install flask-app ./helm/flask-app \
  -f helm/flask-app/values.yaml -f helm/flask-app/values-dev.yaml \
  --set image.repository=<your-dockerhub-user>/devops-capstone \
  -n demo --create-namespace
kubectl get pods -n demo -w
kubectl rollout status deployment/flask-app -n demo
```

### Phase 5 — GitOps with ArgoCD (Day 7–9) ← the differentiator
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
# edit argocd/application.yaml -> repoURL = your fork, then:
kubectl apply -f argocd/application.yaml
kubectl port-forward svc/argocd-server -n argocd 8080:443   # UI at https://localhost:8080
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
```
Now demo the three GitOps superpowers:
1. **Deploy** — push a code change → CI bumps the tag → ArgoCD syncs it. You never ran kubectl.
2. **Drift detection** — `kubectl scale deployment/flask-app -n demo --replicas=5` → watch ArgoCD revert it (selfHeal).
3. **Rollback** — `git revert` the bump commit → the cluster rolls back to the previous SHA.

### Phase 6 — Terraform + EKS (optional, costs money)
```bash
cd terraform
terraform init
terraform plan                 # ALWAYS review the plan
terraform apply
aws eks update-kubeconfig --name devops-capstone-eks --region ap-south-1
# install ArgoCD + apply argocd/application.yaml as in Phase 5
terraform destroy              # IMPORTANT: destroy when done to stop billing
```

---

## Interview talking points (memorize these)

1. **"Push-based vs pull-based CD?"** Push: CI holds cluster credentials and runs helm/kubectl — credentials sprawl, no drift detection. Pull (GitOps): an in-cluster agent (ArgoCD) syncs from Git — least privilege, auditable history, automatic drift correction. I built both and migrated v1→v2.
2. **"How do you roll back?"** `git revert` the tag-bump commit; ArgoCD converges the cluster to the previous SHA. Deterministic because images are SHA-tagged (never `latest`).
3. **"What happens if someone kubectl-edits prod?"** ArgoCD `selfHeal` reverts it; the diff is visible in the UI. Git remains the single source of truth.
4. **"Why did you replace your hand-rolled metrics?"** Gunicorn runs multiple worker processes; a per-process dict means each scrape hits a random worker and counters go backwards. prometheus_client multiprocess mode aggregates samples across workers via a shared mmap directory. (Bonus: labeled counters + histogram buckets enable RED-method dashboards and p95 latency.)
5. **"How does Prometheus find your app?"** In real clusters (kube-prometheus-stack), via a **ServiceMonitor** CRD selecting my Service's named port — pod annotations are ignored there. My compose stack uses a static scrape config instead. Knowing which discovery mechanism applies where matters.
6. **"Container security?"** Multi-stage build, non-root user, `runAsNonRoot`, `readOnlyRootFilesystem` (with an emptyDir for /tmp), `allowPrivilegeEscalation: false`, all capabilities dropped, seccomp RuntimeDefault, Trivy failing the pipeline on HIGH/CRITICAL, secrets only in GitHub Secrets, nodes in private subnets.
7. **"Zero-downtime deployments?"** RollingUpdate with `maxUnavailable: 0` + readiness probes gating traffic. Liveness restarts dead containers; readiness controls traffic — confusing them causes restart loops.
8. **"Why Terraform modules instead of raw resources?"** Battle-tested community modules encode best practices (VPC subnetting, EKS IAM); less code, fewer mistakes, reviewable via `terraform plan`.

## Troubleshooting drills (practice these — they ARE interview questions)

| Break it | Symptom | Fix / diagnosis path |
|---|---|---|
| Set image tag to a nonexistent tag (in Git!) | Pod `ImagePullBackOff`; ArgoCD Degraded | `kubectl describe pod` → Events → revert the commit |
| Set memory limit to 32Mi | `OOMKilled` / CrashLoopBackOff | `kubectl describe pod` shows OOMKilled → raise limits |
| Change probe path to /wrong | Pods never Ready, rollout stuck | readiness failing → `kubectl describe pod` → fix path |
| `kubectl scale` manually | ArgoCD shows OutOfSync, then reverts | this is selfHeal working — explain why it's a feature |
| Break a unit test | Pipeline blocks at Stage 1 | read CI logs → the quality gate doing its job |
| Old CVE-heavy base image | Trivy stage fails | read Trivy report → upgrade base image |
| Forget metrics-server on minikube | HPA target shows `<unknown>` | `minikube addons enable metrics-server` |

## Honest BQA → DevOps experience mapping

- **Test planning / regression** → the CI test stage is a quality gate implemented as pipeline code.
- **Release validation** → ArgoCD sync status + health checks are release validation, automated and continuous.
- **Defect RCA** → the troubleshooting drills use the same discipline: reproduce → isolate → evidence → fix → verify.
- **API testing** → you built and probed the endpoints (`/health`, `/metrics`) you used to test.
- **UAT / acceptance criteria** → per-env values files ≈ environment-specific acceptance criteria.

**Never claim production DevOps experience.** Say: "I have QA/BQA experience and hands-on project experience building a GitOps CI/CD pipeline with Docker, Kubernetes, Helm, ArgoCD, Terraform, GitHub Actions, and Prometheus." Honest and hireable.

## Resume bullets (honest versions)

- Built a GitOps delivery pipeline: GitHub Actions runs tests and Trivy security scans as release gates, pushes SHA-tagged images, and commits the release manifest; ArgoCD (pull-based CD) syncs the cluster with automated drift detection and `git revert` rollbacks.
- Instrumented a Python API with Prometheus (multiprocess-safe counters and latency histograms), exposed via ServiceMonitor to kube-prometheus-stack, and built Grafana RED-method dashboards (request rate, error rate, p95 latency).
- Hardened Kubernetes workloads: non-root, read-only root filesystem, dropped capabilities, seccomp, liveness/readiness probes, HPA autoscaling, zero-downtime rolling updates.
- Provisioned AWS infrastructure (VPC, EKS) with Terraform official modules; nodes in private subnets, remote-state best practices.

## Quick revision notes

- CI = build + test every commit. CD (GitOps) = Git commit *is* the deploy; an agent converges the cluster to Git.
- Docker image = immutable artifact; container = running instance. SHA tags > `latest`.
- Deployment → ReplicaSet → Pods. Service = stable VIP + label-selector load balancing. Ingress = L7 entry point.
- Helm = K8s package manager; one chart, per-env values; ArgoCD renders charts server-side.
- ArgoCD: Application CRD = "sync this repo path to this cluster/namespace"; automated + selfHeal + prune.
- Terraform: init → plan → apply → destroy; state = source of truth; S3 backend + DynamoDB locking in teams.
- Prometheus pulls; multiprocess mode aggregates across gunicorn workers; alert on symptoms (error rate, latency).
