"""
DevOps Capstone Demo API — v2 (GitOps edition).

Endpoints:
  GET /         -> welcome + version + environment
  GET /health   -> health probe used by Docker HEALTHCHECK and K8s liveness/readiness
  GET /api/tasks, POST /api/tasks -> sample business endpoints
  GET /metrics  -> Prometheus metrics via the official prometheus_client

v1 -> v2 metrics lesson (great interview story):
  v1 hand-rolled counters in a plain dict. That silently breaks under
  gunicorn with >1 worker: each worker process has its OWN dict, so
  Prometheus scrapes hit a random worker and counters appear to go
  backwards. v2 uses prometheus_client in *multiprocess mode*: every
  worker writes samples to memory-mapped files in PROMETHEUS_MULTIPROC_DIR
  and /metrics aggregates across all workers.
"""

import os
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

app = Flask(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "2.0.0")
START_TIME = time.time()

# In-memory demo store (a real service would use a database)
TASKS = [
    {"id": 1, "title": "Learn Docker", "done": True},
    {"id": 2, "title": "Deploy with ArgoCD", "done": False},
]

# ---------------------------------------------------------------------------
# Metrics — official client, multiprocess-safe.
# Labels let Grafana slice by endpoint/status: rate(app_requests_total[1m])
# ---------------------------------------------------------------------------
REQUESTS = Counter(
    "app_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status"],
)
LATENCY = Histogram(
    "app_request_latency_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)


@app.before_request
def start_timer():
    g.start = time.time()


@app.after_request
def record_metrics(response):
    endpoint = request.endpoint or "unknown"
    if endpoint != "metrics":  # don't let scrapes pollute app metrics
        REQUESTS.labels(request.method, endpoint, response.status_code).inc()
        LATENCY.labels(endpoint).observe(time.time() - g.get("start", time.time()))
    return response


@app.get("/")
def index():
    return jsonify(
        message="DevOps Capstone API is running",
        version=APP_VERSION,
        environment=os.environ.get("APP_ENV", "local"),
    )


@app.get("/health")
def health():
    """Used by Docker HEALTHCHECK and by K8s liveness AND readiness probes."""
    return jsonify(status="ok", uptime_seconds=round(time.time() - START_TIME, 1))


@app.get("/api/tasks")
def list_tasks():
    return jsonify(tasks=TASKS)


@app.post("/api/tasks")
def add_task():
    data = request.get_json(silent=True)
    # Input validation: never trust client input
    if not data or not isinstance(data.get("title"), str) or not data["title"].strip():
        return jsonify(error="'title' (non-empty string) is required"), 400
    task = {"id": len(TASKS) + 1, "title": data["title"].strip(), "done": False}
    TASKS.append(task)
    return jsonify(task), 201


@app.get("/metrics")
def metrics():
    """Prometheus exposition. Aggregates across gunicorn workers when
    PROMETHEUS_MULTIPROC_DIR is set (see gunicorn_conf.py / Dockerfile)."""
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        payload = generate_latest(registry)
    else:
        payload = generate_latest()  # single-process mode (dev server, pytest)
    return Response(payload, mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    # Dev server only — the Docker image runs gunicorn (see Dockerfile)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
