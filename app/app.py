"""
DevOps Capstone Demo API — matches the project README.

Endpoints:
  GET /         -> welcome + version + environment
  GET /health   -> health probe used by Docker HEALTHCHECK and K8s liveness/readiness
  GET /api/tasks, POST /api/tasks -> sample business endpoints
  GET /metrics  -> Prometheus metrics: app_requests_total, app_request_latency_seconds
"""

import os
import time
from flask import Flask, jsonify, request, g

app = Flask(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
START_TIME = time.time()

# In-memory demo store (a real service would use a database)
TASKS = [
    {"id": 1, "title": "Learn Docker", "done": True},
    {"id": 2, "title": "Deploy with Helm", "done": False},
]

# Minimal hand-rolled metrics (enough for Grafana's rate(app_requests_total[1m]))
METRICS = {"requests_total": 0, "latency_sum": 0.0, "latency_count": 0}


@app.before_request
def start_timer():
    g.start = time.time()
    METRICS["requests_total"] += 1


@app.after_request
def record_latency(response):
    elapsed = time.time() - g.get("start", time.time())
    METRICS["latency_sum"] += elapsed
    METRICS["latency_count"] += 1
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
    """Prometheus exposition format."""
    avg = (METRICS["latency_sum"] / METRICS["latency_count"]) if METRICS["latency_count"] else 0.0
    body = (
        "# HELP app_requests_total Total HTTP requests received\n"
        "# TYPE app_requests_total counter\n"
        f"app_requests_total {METRICS['requests_total']}\n"
        "# HELP app_request_latency_seconds_sum Cumulative request latency\n"
        "# TYPE app_request_latency_seconds_sum counter\n"
        f"app_request_latency_seconds_sum {METRICS['latency_sum']:.6f}\n"
        "# HELP app_request_latency_seconds_count Number of observed requests\n"
        "# TYPE app_request_latency_seconds_count counter\n"
        f"app_request_latency_seconds_count {METRICS['latency_count']}\n"
        "# HELP app_request_latency_seconds_avg Average request latency\n"
        "# TYPE app_request_latency_seconds_avg gauge\n"
        f"app_request_latency_seconds_avg {avg:.6f}\n"
    )
    return body, 200, {"Content-Type": "text/plain; version=0.0.4"}


if __name__ == "__main__":
    # Dev server only — the Docker image runs gunicorn (see Dockerfile)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
