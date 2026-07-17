# DevOps Capstone: End-to-End CI/CD Pipeline

A production-style pipeline you can build, run, break, and explain in interviews:

**Flask API → Docker → GitHub Actions (test + Trivy scan) → Docker Hub → Helm → Kubernetes (EKS or minikube) → Prometheus + Grafana**, with **Terraform** provisioning the AWS infrastructure.

---

## Architecture

```
 Developer pushes code to GitHub (main branch)
        │
        ▼
 GitHub Actions Pipeline
 ├── Stage 1: Unit tests (pytest)          ← quality gate #1
 ├── Stage 2: Docker build + Trivy scan    ← quality gate #2 (DevSecOps)
 ├── Stage 3: Push image (tag = git SHA)
 └── Stage 4: helm upgrade → Kubernetes    ← rolling deployment, zero downtime
        │
        ▼
 Kubernetes Cluster (EKS via Terraform, or minikube locally)
 ├── Deployment (2 replicas, liveness/readiness probes, non-root)
 ├── Service (ClusterIP)
 └── HPA (autoscale 2→5 pods at 70% CPU)
        │
        ▼
 Prometheus scrapes /metrics → Grafana dashboards
```

## Repo layout

```
app/                      Flask app + pytest tests + requirements
Dockerfile                Multi-stage, non-root, healthcheck
docker-compose.yml        Local stack: app + Prometheus + Grafana
monitoring/prometheus.yml Scrape config
.github/workflows/        CI/CD pipeline (ci-cd.yml)
helm/flask-app/           Helm chart (deployment, service, HPA)
terraform/                VPC + EKS via official modules
```

---

## Build it in 5 phases (do them in order)

### Phase 1 — Run locally (Day 1)
```bash
cd app && pip install -r requirements.txt
python app.py                  # visit http://localhost:5000 and /health and /metrics
pytest -v                      # run the tests the pipeline will run
```

### Phase 2 — Containerize (Day 1–2)
```bash
docker build -t devops-capstone:1.0 .
docker run -d -p 5000:5000 --name capstone devops-capstone:1.0
docker logs capstone           # troubleshooting habit: always check logs first
docker compose up --build      # full local stack with Prometheus + Grafana
```
Open Prometheus (localhost:9090) → Status → Targets → confirm the app is UP.
In Grafana (localhost:3000), add Prometheus as a data source (URL: http://prometheus:9090) and graph `rate(app_requests_total[1m])`.

### Phase 3 — CI/CD (Day 3–4)
1. Push this repo to GitHub.
2. Add secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
3. Push a commit → watch the pipeline: tests → Trivy scan → image push.
4. Deliberately break a test and push → watch the pipeline block the release. **This is your favorite demo: quality gates as code.**

### Phase 4 — Kubernetes (Day 5–7)
Free option (recommended first): minikube.
```bash
minikube start
helm upgrade --install flask-app ./helm/flask-app \
  --set image.repository=<your-dockerhub-user>/devops-capstone \
  --set image.tag=latest -n demo --create-namespace
kubectl get pods -n demo -w
kubectl rollout status deployment/flask-app -n demo
minikube service flask-app -n demo    # open the app
```
Then add the `KUBE_CONFIG` secret (base64 of your kubeconfig) so the pipeline deploys automatically.

### Phase 5 — Terraform + EKS (optional, costs money)
```bash
cd terraform
terraform init
terraform plan                 # ALWAYS review the plan (like reviewing a release note)
terraform apply
aws eks update-kubeconfig --name devops-capstone-eks --region ap-south-1
# ...deploy with helm as above...
terraform destroy              # IMPORTANT: destroy when done to stop billing
```

---

