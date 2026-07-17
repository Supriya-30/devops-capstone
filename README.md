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

## Interview talking points (memorize these)

1. **"Why multi-stage Docker build?"** Smaller image (no compilers/build tools), faster pulls, smaller attack surface.
2. **"Why tag images with the git SHA?"** Immutable, traceable artifacts. `latest` is mutable — you can never be sure what's running. SHA tags let me roll back to an exact commit.
3. **"How do you achieve zero-downtime deployment?"** RollingUpdate strategy with `maxUnavailable: 0`, plus readiness probes so traffic only reaches pods that are actually ready.
4. **"Liveness vs readiness probe?"** Liveness restarts a dead container; readiness removes a pod from the Service until it can serve traffic. Confusing them causes restart loops.
5. **"How is security handled?"** Non-root container user, `runAsNonRoot` in the pod spec, Trivy scanning that fails the pipeline on CRITICAL/HIGH CVEs, secrets in GitHub Secrets (never in code), worker nodes in private subnets.
6. **"How would you roll back a bad release?"** `helm rollback flask-app <revision>` or `kubectl rollout undo deployment/flask-app`. Because images are SHA-tagged, rollback is deterministic.
7. **"How do you monitor it?"** App exposes Prometheus metrics (request count, latency); Prometheus scrapes via pod annotations; Grafana dashboards + alerts on error rate/latency (RED method).
8. **"Why Terraform modules instead of raw resources?"** Battle-tested community modules encode best practices (VPC subnetting, EKS IAM); less code, fewer mistakes, reviewable via `terraform plan`.

## Troubleshooting drills (practice these — they ARE interview questions)

| Break it | Symptom | Fix / diagnosis path |
|---|---|---|
| Set image tag to a nonexistent tag | Pod `ImagePullBackOff` | `kubectl describe pod` → check Events → fix tag |
| Set memory limit to 32Mi | Pod `OOMKilled` / CrashLoopBackOff | `kubectl describe pod` shows OOMKilled → raise limits |
| Change health path to /wrong | Pods never Ready, rollout stuck | readiness probe failing → `kubectl describe pod` → fix probe path |
| Break a unit test | Pipeline fails at test stage | Read CI logs → this is the quality gate working as designed |
| Introduce a CVE-heavy base image (e.g. old python:3.8) | Trivy stage fails | Read Trivy report → upgrade base image |

## Honest BQA → DevOps experience mapping (for this project)

- **Test planning / regression testing** → You designed the CI test stage as an automated quality gate. Say: "As a BQA I enforced quality gates manually before releases; in this project I implemented them as pipeline code."
- **Release validation** → The `deploy` job + `kubectl rollout status` verification is release validation, automated.
- **Defect management / troubleshooting** → The troubleshooting drills above use the same root-cause discipline you used triaging defects (reproduce → isolate → evidence → fix → verify).
- **API testing** → You tested REST endpoints; here you built and probed them (`/health`, `/metrics`) and understand status codes, contracts, and probes.
- **Agile/Jira/Azure Boards** → Pipelines map to the same SDLC stages you already know; you can speak to how CI/CD shortens feedback loops in a sprint.
- **UAT / acceptance criteria** → Helm values per environment ≈ environment-specific acceptance criteria; smoke tests post-deploy ≈ your smoke testing experience.

**Never claim production DevOps experience.** Say: "I have X years of QA/BQA experience and hands-on personal-project experience building an end-to-end CI/CD pipeline with Docker, Kubernetes, Helm, Terraform, GitHub Actions, and Prometheus." That is honest and hireable.

## Resume bullets (honest versions)

- Built an end-to-end CI/CD pipeline (GitHub Actions) with automated unit tests and Trivy container security scanning as release quality gates, deploying a Dockerized Python API to Kubernetes via Helm with zero-downtime rolling updates.
- Provisioned AWS infrastructure (VPC, EKS) using Terraform with official modules and remote-state best practices.
- Implemented observability with Prometheus custom metrics and Grafana dashboards; configured Kubernetes liveness/readiness probes and HPA-based autoscaling.
- Leveraged 4+ years of BQA experience (test planning, release validation, defect RCA) to design pipeline quality gates and post-deployment verification.

## Quick revision notes

- CI = build + test on every commit. CD = automated, gated deployment.
- Docker image = immutable artifact; container = running instance.
- Deployment → ReplicaSet → Pods. Service = stable virtual IP + load balancing via label selectors.
- Helm = package manager for K8s; one chart, per-env values files; `helm rollback` for instant rollback.
- Terraform: init → plan → apply → destroy; state file is the source of truth; use S3 backend + DynamoDB locking in teams.
- Rolling vs Blue-Green vs Canary: gradual replace vs full-environment switch vs small-percentage traffic testing.
- Prometheus pulls metrics; Grafana visualizes; alert on symptoms (error rate, latency), not just causes.
