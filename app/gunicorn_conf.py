# Gunicorn config — wired in by the Dockerfile CMD.
#
# Why this file exists: prometheus_client multiprocess mode needs
# 1) PROMETHEUS_MULTIPROC_DIR to exist before workers start
#    (with readOnlyRootFilesystem the image's baked-in dir is shadowed
#    by the emptyDir volume mounted at /tmp, so create it at boot), and
# 2) stale worker files to be cleaned up when a worker dies, otherwise
#    dead workers' counters are aggregated forever.

import os

bind = "0.0.0.0:5000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))


def on_starting(server):
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        os.makedirs(mp_dir, exist_ok=True)


def child_exit(server, worker):
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
