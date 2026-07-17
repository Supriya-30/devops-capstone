# ---------- Stage 1: builder ----------
# Multi-stage build: final image contains no pip cache or build tooling.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

# Security: never run containers as root
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/app.py .

ENV PORT=5000 \
    APP_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 5000
USER appuser

# Docker-level healthcheck (K8s uses its own probes against /health)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# gunicorn = production WSGI server; flask's dev server is not production-safe
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
