"""
Gunicorn configuration for Hospital Platform production deployment (Phase 17).
Serves the Django WSGI application with environment-driven concurrency,
timeouts, keepalive, and container-friendly stdout/stderr logging.
"""
import multiprocessing
import os

# Server socket binding
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker concurrency
# In containers, workers can be overridden via GUNICORN_WORKERS
default_workers = max(2, min(multiprocessing.cpu_count() * 2, 4))
workers = int(os.environ.get("GUNICORN_WORKERS", default_workers))
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "sync")
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_connections = 1000

# Connection timeouts & keepalive
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", 5))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Process naming
proc_name = "hospital_platform_gunicorn"

# Logging configuration - streams to stdout/stderr for Docker capture
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
capture_output = True

# Request and Header limits (Security hardening)
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
