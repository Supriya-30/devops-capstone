"""Unit tests — Stage 1 quality gate in the CI pipeline. Run with: pytest -v"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_index_returns_version(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.get_json()
    assert "version" in body and "environment" in body


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_list_tasks(client):
    res = client.get("/api/tasks")
    assert res.status_code == 200
    assert isinstance(res.get_json()["tasks"], list)


def test_add_task_valid(client):
    res = client.post("/api/tasks", json={"title": "Write Terraform"})
    assert res.status_code == 201
    assert res.get_json()["title"] == "Write Terraform"


def test_add_task_invalid(client):
    assert client.post("/api/tasks", json={}).status_code == 400
    assert client.post("/api/tasks", json={"title": "   "}).status_code == 400


def test_metrics_exposes_counters(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert b"app_requests_total" in res.data
    assert b"app_request_latency_seconds" in res.data
