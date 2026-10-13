# Production Deployment Guide & Runbook

## Provenance: Phase 0 Foundation → Phase 17 Production Deployment

**Hospital Platform — Production Deployment Runbook**

---

## Table of Contents
1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Environment Variables](#3-environment-variables)
4. [Build Process](#4-build-process)
5. [Docker Compose Startup](#5-docker-compose-startup)
6. [Database Migrations](#6-database-migrations)
7. [Static Asset Collection](#7-static-asset-collection)
8. [Creating & Managing Admin Accounts](#8-creating--managing-admin-accounts)
9. [Health Checks](#9-health-checks)
10. [Nginx Reverse Proxy](#10-nginx-reverse-proxy)
11. [Gunicorn Application Server](#11-gunicorn-application-server)
12. [Celery Worker](#12-celery-worker)
13. [Celery Beat](#13-celery-beat)
14. [PostgreSQL Backup Strategy](#14-postgresql-backup-strategy)
15. [Database Restore Procedure](#15-database-restore-procedure)
16. [Logging Infrastructure](#16-logging-infrastructure)
17. [Monitoring & Observability](#17-monitoring--observability)
18. [HTTPS & TLS Readiness](#18-https--tls-readiness)
19. [Safe Rollback Procedure](#19-safe-rollback-procedure)
20. [Troubleshooting Guide](#20-troubleshooting-guide)

---

## 1. Architecture

The production architecture for the Hospital Platform is designed around modular, containerized services interconnected over an isolated Docker network (`hospital_network`). External HTTP/S traffic terminates at Nginx, which acts as the single public gateway.

```text
                                  PUBLIC INTERNET
                                         │
                                         ▼
                             ┌───────────────────────┐
                             │  Nginx Reverse Proxy  │ (Port 80 / 443)
                             │     (Reverse Proxy)   │
                             └───────────┬───────────┘
                                         │
                  ┌──────────────────────┼──────────────────────┐
                  │                      │                      │
                  ▼                      ▼                      ▼
          ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
          │ React Static  │      │   /api/ and   │      │ Static/Media  │
          │ Assets (SPA)  │      │    /admin/    │      │ Cache Volumes │
          └───────────────┘      └───────┬───────┘      └───────────────┘
                                         │
                                         ▼
                             ┌───────────────────────┐
                             │    Gunicorn / WSGI    │ (Port 8000 internal)
                             │     Django Backend    │
                             └───────┬───────┬───────┘
                                     │       │
                     ┌───────────────┘       └───────────────┐
                     ▼                                       ▼
         ┌───────────────────────┐               ┌───────────────────────┐
         │ PostgreSQL 16 (DB)    │               │ Redis 7 In-Memory     │
         │ - Row-level Locks     │               │ - Cache & Throttling  │
         │ - Relational Data     │               │ - Celery Task Broker  │
         └───────────────────────┘               └───────────┬───────────┘
                                                             │
                                             ┌───────────────┴───────────────┐
                                             ▼                               ▼
                                 ┌───────────────────────┐       ┌───────────────────────┐
                                 │ Celery Worker         │       │ Celery Beat           │
                                 │ - Async Notifications │       │ - Scheduled Reminders │
                                 │ - Transaction safe    │       │ - 30-min Idempotent   │
                                 └───────────────────────┘       └───────────────────────┘
```

### Network Isolation Policy
- Only the **Nginx** service exposes public ports (`80`, `443`).
- **Backend**, **Worker**, and **Beat** communicate with **PostgreSQL** (`db:5432`) and **Redis** (`redis:6379`) exclusively via internal Docker network DNS.
- PostgreSQL and Redis have persistent Docker volumes (`postgres_data`, `redis_data`) ensuring state persistence across container teardown.

---

## 2. Prerequisites

Ensure the deployment host environment meets the following baseline requirements:

| Component | Minimum Version | Recommended Specification |
|---|---|---|
| OS | Ubuntu 22.04 LTS / Debian 12 / RHEL 9 | Linux 64-bit kernel ≥ 5.15 |
| CPU | 2 Cores | 4 Cores |
| RAM | 4 GB | 8 GB |
| Disk | 30 GB SSD | 80 GB SSD (volume expansion for DB) |
| Docker Engine | 24.0+ | Docker CE 26.0+ |
| Docker Compose | v2.20+ | Docker Compose v2.26+ |
| OpenSSL | 1.1.1+ | 3.0+ (for TLS certificates) |
| Network | Ports 80 & 443 open inbound | Unfiltered egress for SMTP & Cloudinary |

Verify installation on host:
```bash
docker --version
docker compose version
```

---

## 3. Environment Variables

All secrets, infrastructure connections, and toggles must be configured via a `.env` file at the root of the repository. A template is maintained at `.env.example`.

### Key Environment Parameters

```ini
# --- Django Core ---
DJANGO_SECRET_KEY=generate_a_secure_random_64_character_key_here
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=hospital.example.com,localhost,backend,nginx
CORS_ALLOWED_ORIGINS=https://hospital.example.com,http://localhost
CSRF_TRUSTED_ORIGINS=https://hospital.example.com,http://localhost

# --- Database (PostgreSQL) ---
POSTGRES_DB=hospital_db
POSTGRES_USER=hospital_user
POSTGRES_PASSWORD=production_super_strong_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

# --- Redis & Celery ---
REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# --- JWT Configuration ---
JWT_ACCESS_MINUTES=60
JWT_REFRESH_DAYS=7

# --- Gunicorn Production Server ---
GUNICORN_WORKERS=3
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=120
REST_FRAMEWORK_NUM_PROXIES=1

# --- Media Storage (Cloudinary) ---
CLOUDINARY_CLOUD_NAME=hospital-production
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret

# --- Email Notifications (SMTP) ---
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your_transactional_smtp_token
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=notifications@hospital.example.com

# --- Public Web Gateway (Nginx) ---
NGINX_PORT=80
```

> [!CAUTION]
> Never commit `.env` containing production passwords or API keys to Git. Ensure `.gitignore` includes `.env`.

---

## 4. Build Process

The project provides multi-stage, production-optimized container images for each tier:

### 1. Validate Docker Compose Configuration
```bash
docker compose config
```

### 2. Build Container Images
Build all images without using cached layers to guarantee clean dependency trees:
```bash
docker compose build --no-cache
```

### Image Build Overview
- **`backend`**: Built from `docker/backend/Dockerfile` on `python:3.12-slim`. Installs `libpq-dev`, `curl`, and all dependencies in `backend/requirements.txt`. Exposes Gunicorn on port 8000.
- **`celery_worker` / `celery_beat`**: Built from `docker/celery/Dockerfile` on `python:3.12-slim`. Runs Celery app worker or Beat scheduler.
- **`frontend`**: Built from `docker/frontend/Dockerfile` on `node:20-alpine`. Builds production bundle via `npm run build` and runs Vite preview.
- **`nginx`**: Built from `docker/nginx/Dockerfile`. Multi-stage build compiles React assets and copies production bundles directly into `/var/www/frontend`.

---

## 5. Docker Compose Startup

Start the complete 7-service stack in detached daemon mode:

```bash
docker compose up -d
```

### Verify Service Status
```bash
docker compose ps
```
Expected output:
```text
NAME                     SERVICE         STATUS                    PORTS
hospital_backend         backend         Up (healthy)              8000/tcp
hospital_celery_beat     celery_beat     Up                        
hospital_celery_worker   celery_worker   Up                        
hospital_frontend        frontend        Up                        3000/tcp
hospital_nginx           nginx           Up (healthy)              0.0.0.0:80->80/tcp
hospital_postgres        db              Up (healthy)              5432/tcp
hospital_redis           redis           Up (healthy)              6379/tcp
```

### Viewing Aggregated Logs
```bash
docker compose logs -f --tail=100
```

---

## 6. Database Migrations

Database schema migrations are **never** executed during Docker image build. They must be executed during the deployment lifecycle step:

### 1. Check for Pending Model Changes
Verify that code matches migrations:
```bash
docker compose exec backend python manage.py makemigrations --check --dry-run
```
*(Must output `No changes detected`)*

### 2. Run Database Migrations
Apply migrations against the PostgreSQL container:
```bash
docker compose exec backend python manage.py migrate --noinput
```

### 3. Verify Applied Migrations
```bash
docker compose exec backend python manage.py showmigrations
```

---

## 7. Static Asset Collection

Django administrative and DRF browsable API static files must be collected into the shared Docker volume (`static_volume`) so Nginx can serve them directly:

```bash
docker compose exec backend python manage.py collectstatic --noinput
```

Assets are written to `/app/staticfiles` inside the container, which is mounted read-only into Nginx at `/app/staticfiles`.

---

## 8. Creating & Managing Admin Accounts

### Create Superuser Non-Interactively
```bash
docker compose exec -e DJANGO_SUPERUSER_PASSWORD="SecureAdminPassword123!" \
  backend python manage.py createsuperuser \
  --username hospital_admin \
  --email admin@hospital.example.com \
  --noinput
```

### Accessing Django Admin
Navigate to `http://<your-domain-or-ip>/admin/` and authenticate using the credentials created above.

---

## 9. Health Checks

The platform includes two levels of automated health monitoring:

### 1. Gateway Health Check (Nginx)
Probes Nginx reverse-proxy responsiveness:
```bash
curl -f http://localhost/health
```
Response:
```json
{"status":"ok","service":"hospital-platform-nginx"}
```

### 2. Basic Backend Health Check
Probes Django WSGI server availability:
```bash
curl -f http://localhost/api/health/
```
Response:
```json
{"status":"ok","service":"hospital-platform-api"}
```

### 3. Deep Infrastructure Health Check (`?detailed=1`)
Executes live probes against both PostgreSQL (`SELECT 1;`) and Redis cache:
```bash
curl -f http://localhost/api/health/?detailed=1
```
Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "service": "hospital-platform-api"
}
```

---

## 10. Nginx Reverse Proxy

Nginx acts as the single frontend reverse proxy, routing requests and enforcing client connection security.

- Configuration file: `nginx/nginx.conf`
- **Routing Rules**:
  - `/` -> Serves React SPA static files from `/var/www/frontend`.
  - `try_files $uri $uri/ /index.html` -> Enables React Router client-side routing.
  - `/api/` -> Proxied to `http://backend:8000/api/` with proxy headers.
  - `/admin/` -> Proxied to `http://backend:8000/admin/`.
  - `/static/` -> Directly served from `/app/staticfiles/` with caching headers.
  - `/health` -> Returns `200 OK` JSON directly.
- **Client IP Preservation**:
  - `proxy_set_header X-Real-IP $remote_addr;`
  - `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`
  - `proxy_set_header X-Forwarded-Proto $scheme;`
  Enables DRF Redis throttling to track real client IP addresses.
- **Payload Limits**: `client_max_body_size 15M;` (accommodates Cloudinary media uploads up to 5MB plus form metadata).

---

## 11. Gunicorn Application Server

Gunicorn serves the Django WSGI application in production.

- Configuration file: `backend/gunicorn.conf.py`
- Command: `gunicorn config.wsgi:application -c gunicorn.conf.py`
- Default Settings:
  - Workers: `3` (Formula: `(2 x CPU Cores) + 1`)
  - Threads: `2` per worker
  - Worker Class: `gthread`
  - Timeout: `120` seconds
  - Keepalive: `5` seconds
  - Max Requests: `1000` with `jitter=50` (prevents memory leaks by recycling workers periodically)
  - Access & Error Logs: Emitted directly to `stdout` / `stderr`.

---

## 12. Celery Worker

The Celery worker executes asynchronous tasks in background queues.

- Container: `hospital_celery_worker`
- Command: `celery -A config worker --loglevel=info --concurrency=2 -E`
- **Responsibilities**:
  - Dispatches appointment booking confirmation emails
  - Dispatches appointment cancellation and reschedule notifications
  - Sends internal staff and administrative audit alerts
  - Handles temporary SMTP network retries with exponential backoff (up to 3 retries)
  - Honors transactional safety (`transaction.on_commit()`) so failed DB commits never queue orphaned emails.

### Inspecting Worker Status
```bash
docker compose logs celery_worker --tail=50
```

---

## 13. Celery Beat

Celery Beat triggers scheduled recurring workflows.

- Container: `hospital_celery_beat`
- Command: `celery -A config beat --loglevel=info --scheduler=django_celery_beat.schedulers:DatabaseScheduler`
- **Schedule**: Every 30 minutes (`apps.notifications.tasks.send_appointment_reminders_batch_task`)
- **Idempotency Guarantee**: Scans appointments occurring within the upcoming 24-hour window, skips already-reminded appointments, and isolates failure per recipient.

### Inspecting Beat Status
```bash
docker compose logs celery_beat --tail=50
```

---

## 14. PostgreSQL Backup Strategy

### Backup Frequency & Retention Policy
| Tier | Frequency | Tool | Retention | Storage Location |
|---|---|---|---|---|
| Full Snapshot | Daily at 02:00 UTC | `pg_dump` custom format | 30 days | Encrypted remote bucket (S3 / GCS) |
| Pre-Deploy | Before each release | `pg_dump` | 7 days | Local / Staging backup storage |
| Transaction Logs | Continuous (WAL) | Barman / pgBackRest (optional enterprise) | 7 days | Cold storage |

### Live Database Backup Command
Execute non-locking transactional dump directly from the running PostgreSQL container:

```bash
# Create backup directory
mkdir -p ./backups

# Execute pg_dump (Custom compressed format -Fc)
docker compose exec -T db pg_dump \
  -U hospital_user \
  -d hospital_db \
  -F c \
  -b \
  -v > ./backups/hospital_db_$(date +%Y%m%d_%H%M%S).dump
```

To backup in plain SQL format:
```bash
docker compose exec -T db pg_dump \
  -U hospital_user \
  -d hospital_db \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges > ./backups/hospital_db_$(date +%Y%m%d_%H%M%S).sql
```

### Backup Verification
Automate periodic restoration of dumps into a temporary staging database to verify file integrity and data completeness.

---

## 15. Database Restore Procedure

> [!WARNING]
> Restoring a database overwrites existing data. Always take a fresh safety dump before restoring!

### Step-by-Step Restoration Runbook

#### 1. Stop Application Services
Stop containers that write to the database:
```bash
docker compose stop backend celery_worker celery_beat
```

#### 2. Terminate Active Connections & Restore
```bash
# Option A: Restoring from Custom Format (.dump)
docker compose exec -T db pg_restore \
  -U hospital_user \
  -d hospital_db \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -v < ./backups/hospital_db_20261009_013000.dump

# Option B: Restoring from SQL Format (.sql)
docker compose exec -T db psql \
  -U hospital_user \
  -d hospital_db < ./backups/hospital_db_20261009_013000.sql
```

#### 3. Run Missing Migrations
```bash
docker compose exec backend python manage.py migrate --noinput
```

#### 4. Restart Services & Validate
```bash
docker compose start backend celery_worker celery_beat
curl -f http://localhost/api/health/?detailed=1
```

---

## 16. Logging Infrastructure

The platform implements standard Unix 12-factor logging streaming directly to `stdout` and `stderr`.

- **Django / Gunicorn**: Formatted as `[{asctime}] [{levelname}] [{name}:{lineno}] {message}`.
- **Sensitive Data Masking**: Passwords, JWT tokens, Cloudinary secrets, and credit/health card details are stripped by custom exception handlers and log filters.
- **Docker Log Driver**: Centralized log collection via standard Docker commands:
  ```bash
  # Follow backend logs
  docker compose logs -f backend

  # View Nginx access & error traffic
  docker compose logs -f nginx

  # View background tasks
  docker compose logs -f celery_worker
  ```

---

## 17. Monitoring & Observability

### Health API Integration
Connect synthetic monitoring (UptimeRobot, Datadog, Prometheus Blackbox, CloudWatch) to:
- Gateway check: `GET http://<host>/health`
- Deep component check: `GET http://<host>/api/health/?detailed=1`

### Metrics & Error Monitoring Integration
- The codebase provides structured error logging in `config.exceptions.custom_exception_handler`.
- When integrating Sentry or OpenTelemetry, set `SENTRY_DSN` in `.env` without modifying application business logic.
- Celery task events are enabled (`-E` flag) for monitoring with Celery Flower:
  ```bash
  # Launch Flower monitoring UI (optional)
  docker run -d -p 5555:5555 --network eglesorahospitalprojectbuharsh_hospital_network mher/flower celery --broker=redis://redis:6379/0
  ```

---

## 18. HTTPS & TLS Readiness

### Production TLS Termination Setup

In production, terminate SSL at Nginx or at an upstream cloud load balancer (e.g. AWS ALB, Cloudflare, GCP Cloud Load Balancer).

#### 1. Obtain Certificates (Let's Encrypt / Certbot)
```bash
sudo certbot certonly --standalone -d hospital.example.com
```

#### 2. Update `nginx/nginx.conf`
Uncomment the HTTPS block in `nginx/nginx.conf`:
```nginx
server {
    listen 80;
    server_name hospital.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name hospital.example.com;

    ssl_certificate /etc/letsencrypt/live/hospital.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hospital.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... remaining location blocks ...
}
```

#### 3. Update `.env` Security Flags
```ini
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
```

---

## 19. Safe Rollback Procedure

When a deployment must be rolled back, follow this structured, risk-mitigated procedure.

> [!IMPORTANT]
> **Never blindly execute `migrate <app> <previous_migration>` in production!**
> Reversing migrations can drop columns and permanently destroy user data created during the failed release. Prefer forward-fixing or database snapshot restoration.

### Step 1: Identify Deployment Failure Scope
- **Frontend-only bug**: Revert Nginx or frontend image tag. Database remains intact.
- **Backend logic error (no DB change)**: Revert backend image to previous tag.
- **Schema incompatibility**: Restore PostgreSQL snapshot taken immediately prior to deployment.

### Step 2: Roll Back Application Containers
Pin previous stable image versions in `docker-compose.yml` or pull previous release tags:
```bash
docker compose stop backend celery_worker celery_beat frontend
docker compose up -d backend celery_worker celery_beat frontend
```

### Step 3: Worker & Beat Graceful Shutdown
Celery workers should be stopped with `SIGTERM` so currently running appointment confirmation emails complete cleanly without duplication:
```bash
docker compose stop -t 30 celery_worker
```

### Step 4: Verification
Confirm system health following rollback:
```bash
curl -f http://localhost/health
curl -f http://localhost/api/health/?detailed=1
```

---

## 20. Troubleshooting Guide

| Issue | Likely Cause | Solution |
|---|---|---|
| `502 Bad Gateway` on `/api/` | Backend container is starting or crashed | Check `docker compose logs backend`. Ensure PostgreSQL and Redis are healthy. |
| DB Connection Refused | PostgreSQL container not ready | Verify `docker compose ps db`. Check PostgreSQL logs: `docker compose logs db`. |
| Celery tasks not executing | Redis broker down or worker hung | Check `docker compose logs celery_worker`. Restart worker: `docker compose restart celery_worker`. |
| Static files missing / 404 on `/static/admin/` | `collectstatic` was not run | Run `docker compose exec backend python manage.py collectstatic --noinput`. |
| Rate limiting triggering unexpectedly (`429`) | Proxy headers not set / client IP spoofed | Verify `REST_FRAMEWORK_NUM_PROXIES=1` in `.env` and `X-Forwarded-For` in `nginx.conf`. |
| CORS / CSRF verification failed | Domain not registered in origins | Add client domain to `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` in `.env`. |

---
