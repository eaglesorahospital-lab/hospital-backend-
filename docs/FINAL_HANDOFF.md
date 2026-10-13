# Project Handoff & Production Operational Runbook

**Eagle Sora Hospital Platform — Phase 18 Final Handoff**

---

## 1. Project Summary

The Eagle Sora Hospital Platform is a full-stack, enterprise healthcare and hospital management platform designed for hospital outpatient departments, clinical administration, doctor roster scheduling, and transactional patient booking. 

The application architecture strictly adheres to the requirements established in the **Hospital Platform Production Website Intern Assignment**, delivering an authoritative backend with PostgreSQL row-level concurrency protection, asynchronous Celery notifications, validated Cloudinary media handling, enterprise security hardening, and a containerized 7-service Docker Compose deployment stack.

All development phases (**Phases 0 through 18**) are complete, verified, and passing regression testing.

---

## 2. Implemented Features & Modules

### 2.1 Public Institutional Hospital Website
- **Institutional Identity**: Public homepage modeled after established hospital institutions (e.g., Bombay Hospital and Netralaya) featuring clinical trust markers, institutional overview, contact directories, and emergency care notices.
- **Departments & Clinical Services**: Full directory of departments with specialized diagnostic facilities, clinical services, and departmental FAQs.
- **Doctor Directory & Schedules**: Doctor profiles with qualifications, biographies, department affiliations, specialties, Cloudinary profile media, and real-time weekly schedule summaries.
- **Facilities & Announcements**: Hospital infrastructure facilities catalog and administrative announcements.

### 2.2 Appointment Booking & Availability Engine
- **Deterministic Slot Generator**: Generates 30-minute booking intervals adhering to doctor shift schedules, break intervals, and approved leaves.
- **PostgreSQL Concurrency Protection**: Atomic transactions using `select_for_update()` to enforce row-level locking during booking, guaranteeing that simultaneous booking attempts for the same doctor slot result in exactly one booking (`201 Created`) and subsequent attempts receive `409 Conflict`.
- **Idempotency Protection**: Client-provided `Idempotency-Key` headers ensure network retries do not create duplicate appointments.
- **Appointment Lifecycle**: States: `PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`, `RESCHEDULED`.
- **Cancellation & Rescheduling**: Secure patient and administrative cancellation and slot reassignment workflows.

### 2.3 Patient Self-Service Portal
- **Patient Registration & Login**: Public registration creating `PATIENT` role users and automatically provisioning a `PatientProfile` with a unique Medical Record Number (MRN).
- **Patient Dashboard**: View upcoming and historical appointments, profile information, and appointment status history.
- **Self-Service Actions**: Cancel or reschedule own appointments with strict object-level authorization.

### 2.4 Administrative Operations Portal
- **Hospital Administration**: Manage institutional profile, clinical facilities, and public announcements.
- **Clinical Department Management**: Maintain departments, services, and FAQs.
- **Doctor Roster Management**: Configure doctor profiles, shift schedules, breaks, and leave requests.
- **Audit Log Inspection**: Review administrative mutation records and system events.

### 2.5 Asynchronous Notification Pipeline
- **Celery Task Worker**: Asynchronous dispatch of appointment confirmation, cancellation, rescheduling, and staff alert emails.
- **Bounded Exponential Backoff**: Automatic retry for temporary SMTP network failures (up to 3 retries: 5s, 10s, 20s).
- **Transaction Safety**: Tasks are queued via `transaction.on_commit()`, preventing task dispatch if a database transaction rolls back.
- **Failure Isolation**: An email provider failure never aborts or rolls back an appointment booking.
- **Periodic Reminders (Celery Beat)**: Scheduled task running every 30 minutes to scan upcoming appointments within 24 hours and send reminders idempotently.

### 2.6 Cloudinary Media Management
- **Image Validation**: Binary inspection via Pillow, 5MB file size limit, and MIME type whitelisting (`image/jpeg`, `image/png`, `image/webp`).
- **Safe Replacement**: Uploads and validates new images before persisting references in PostgreSQL, destroying superseded assets in Cloudinary only after database commit.
- **Secret Masking**: Cloudinary credentials and error traces are masked from all API serializers and error payloads.

### 2.7 Security Hardening & Throttling
- **Rate Limiting (Redis-backed)**: Abuse protection on login (5/min), registration (3/min), refresh (10/min), booking (10/min), and photo upload (10/min).
- **IDOR Protection**: Object-level permissions prevent patients from accessing or mutating other patients' appointments or records.
- **Sanitized Errors**: In production mode (`DEBUG=False`), unhandled 500 errors return clean JSON without leaking stack traces or database connection strings.
- **Security Headers**: Standard enforcement of `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: same-origin`.

---

## 3. Technology Stack Reference

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Frontend UI | React | 18.3.x | Single Page Application framework |
| UI Components | Bootstrap | 5.3.x | Accessible clinical UI components |
| Build Tool | Vite | 5.4.x | Frontend compilation and asset bundling |
| Backend API | Django | 5.1.x | Core web framework |
| REST Framework | DRF | 3.17.x | RESTful API serialization & viewsets |
| Database | PostgreSQL | 16-alpine | ACID relational database with row locks |
| In-Memory Cache | Redis | 7-alpine | Application cache, rate limiter & broker |
| Task Queue | Celery | 5.6.x | Asynchronous background job worker |
| Periodic Scheduler | Celery Beat | 2.9.x | Periodic appointment reminder scanner |
| WSGI Server | Gunicorn | 26.x | Production WSGI application server |
| Ingress / Proxy | Nginx | 1.31-alpine | Reverse proxy, static server & gateway |
| Containerization | Docker & Compose | v2+ | Multi-service production deployment |
| Media Storage | Cloudinary & Pillow | 10.x | Image upload, processing & hosting |
| Auth Tokens | SimpleJWT | 5.5.x | JWT authentication with token blacklist |

---

## 4. Repository Structure

```text
hospital-platform/
├── backend/                    # Django & DRF Backend service
│   ├── apps/
│   │   ├── accounts/           # User model, Patient profiles, auth & RBAC
│   │   ├── hospital/           # Hospital info, facilities, announcements, media
│   │   ├── departments/        # Clinical departments & services
│   │   ├── doctors/            # Doctor profiles, specialties, schedules
│   │   ├── scheduling/         # Working days, shifts, breaks, leaves, overrides
│   │   ├── appointments/       # Booking engine, slot generator, concurrency locks
│   │   └── notifications/      # Notifications, audit logs, Celery tasks
│   ├── config/                 # Settings, URLs, WSGI, Celery configuration
│   ├── gunicorn.conf.py        # Production Gunicorn WSGI configuration
│   ├── manage.py               # Django management script
│   └── requirements.txt        # Backend Python dependencies
├── frontend/                   # React + Bootstrap 5 Frontend SPA
│   ├── public/                 # Static public files & institutional emblems
│   ├── src/                    # Components, pages, hooks, services, routes
│   ├── package.json            # Frontend npm scripts & dependencies
│   └── vite.config.js          # Vite build configuration
├── docker/                     # Container configurations
│   ├── backend/Dockerfile      # Production Python 3.12-slim backend image
│   ├── celery/Dockerfile       # Production Celery worker & Beat image
│   ├── frontend/Dockerfile     # Node 20-alpine frontend preview image
│   └── nginx/Dockerfile        # Multi-stage Nginx + compiled frontend image
├── nginx/
│   └── nginx.conf              # Production Nginx reverse proxy configuration
├── database/                   # Database seeds and SQL references
├── docs/                       # Technical & operational documentation
│   ├── API.md                  # Complete REST API specification
│   ├── ARCHITECTURE.md         # System architecture & Mermaid sequence flows
│   ├── DEPLOYMENT.md           # 20-topic production deployment & runbook
│   ├── ERD.md                  # Entity Relationship Diagram & model schemas
│   ├── TESTING.md              # Testing guide & security verification
│   └── FINAL_HANDOFF.md        # Comprehensive project handoff & checklist
├── tests/                      # Automated test suites (198 tests)
├── docker-compose.yml          # Production 7-service orchestration
├── .env.example                # Safe environment configuration template
├── .gitignore                  # Git hygiene & secret exclusion rules
└── README.md                   # Project overview & documentation index
```

---

## 5. Local Startup Instructions (Development Host)

### 5.1 Backend Local Execution
```bash
# 1. Activate Python virtual environment
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/macOS

# 2. Run system checks
python backend/manage.py check

# 3. Apply database migrations
python backend/manage.py migrate

# 4. Start local development server
python backend/manage.py runserver 0.0.0.0:8000
```

### 5.2 Frontend Local Execution
```bash
cd frontend
npm install
npm run dev
```
Accessible at `http://localhost:3000`.

---

## 6. Docker Startup Instructions (Production Stack)

### 6.1 Validate & Start Containers
```bash
# Validate Compose file
docker compose config

# Build and start all 7 services
docker compose up -d --build
```

### 6.2 Service Health Verification
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

### 6.3 Collect Static Assets & Run Migrations
```bash
docker compose exec backend python manage.py collectstatic --noinput
docker compose exec backend python manage.py migrate --noinput
```

### 6.4 Create Superuser Account
```bash
docker compose exec -e DJANGO_SUPERUSER_PASSWORD="SecureAdminPassword123!" \
  backend python manage.py createsuperuser \
  --username hospital_admin \
  --email admin@hospital.example.com \
  --noinput
```

---

## 7. Environment Setup & Secret Hygiene

Configure production parameters in `.env` based on `.env.example`:

| Environment Parameter | Required Setting | Production Guidance |
|---|---|---|
| `DJANGO_SECRET_KEY` | High-entropy string | 64+ random characters |
| `DJANGO_DEBUG` | `False` | Must remain `False` in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated domains | Explicit domain name & internal aliases |
| `POSTGRES_DB` / `DB_NAME` | Database name | `hospital_db` |
| `POSTGRES_USER` / `DB_USER` | Database user | Non-root database role |
| `POSTGRES_PASSWORD` | Strong password | High-entropy password |
| `REDIS_URL` | Redis URL | `redis://redis:6379/1` |
| `CELERY_BROKER_URL` | Celery broker | `redis://redis:6379/0` |
| `CLOUDINARY_*` | Cloudinary API keys | Live cloud account keys |
| `EMAIL_*` | SMTP credentials | Production transactional email provider |
| `REST_FRAMEWORK_NUM_PROXIES` | `1` | Enforces client IP behind Nginx |

---

## 8. Test Execution Instructions

Run all 198 automated regression tests against live PostgreSQL and Redis:

```powershell
.venv\Scripts\python.exe tests/test_foundation.py
.venv\Scripts\python.exe tests/test_backend_foundation.py
.venv\Scripts\python.exe tests/test_domain_models.py
.venv\Scripts\python.exe tests/test_api_layer.py
.venv\Scripts\python.exe tests/test_authentication_rbac.py
.venv\Scripts\python.exe tests/test_appointment_booking.py
.venv\Scripts\python.exe tests/test_celery_notifications.py
.venv\Scripts\python.exe tests/test_cloudinary_media.py
.venv\Scripts\python.exe tests/test_security_hardening.py
```

All 9 test suites pass 100% with zero errors.

---

## 9. Key Documentation References

- **API Documentation**: [`docs/API.md`](API.md) — 750-line complete specification of endpoints, permissions, request schemas, pagination, and response formats.
- **Architecture Documentation**: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — Complete component topology, service interactions, and Mermaid sequence diagrams.
- **Database Schema (ERD)**: [`docs/ERD.md`](ERD.md) — PostgreSQL entity relationships, constraint rules, choices, and foreign keys.
- **Deployment Guide**: [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) — 20-topic production guide, Gunicorn configs, Nginx reverse proxy, static handling, and troubleshooting.
- **Testing Guide**: [`docs/TESTING.md`](TESTING.md) — QA methodology, test suite breakdown, concurrency verification, and security testing.

---

## 10. Backup, Restore & Rollback Procedures

### 10.1 Backup Command
```bash
docker compose exec -T db pg_dump -U hospital_user -d hospital_db -F c -b -v > ./backups/hospital_db_$(date +%Y%m%d_%H%M%S).dump
```

### 10.2 Restore Command
```bash
docker compose stop backend celery_worker celery_beat
docker compose exec -T db pg_restore -U hospital_user -d hospital_db --clean --if-exists --no-owner --no-privileges -v < ./backups/backup.dump
docker compose exec backend python manage.py migrate --noinput
docker compose start backend celery_worker celery_beat
```

### 10.3 Rollback Principle
Never blindly reverse migrations in production (`migrate <app> <previous>`). Use tag-based container image rollbacks or snapshot restorations as documented in [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) Section 19.

---

## 11. Known Limitations & External Integrations

1. **Transactional Email (SMTP)**: Local automated test suites execute against mock backends (`locmem`). Real outward dispatch requires valid SMTP credentials in `.env`.
2. **Cloudinary Media Storage**: Automated tests mock Cloudinary HTTP responses. Real image storage in the cloud requires valid Cloudinary credentials in `.env`.
3. **Public HTTPS / TLS**: Nginx is prepared for TLS termination on port 443 with modern ciphers, but requires mounting a real public certificate (e.g., Let's Encrypt) and public DNS routing.
4. **Public Internet Deployment**: The system has been validated in a complete local multi-container Docker environment; public internet deployment requires an active virtual private cloud (VPC), domain registration, and cloud provider provisioning.

---

## 12. Recommended Operational Checklist for Project Owner

Before opening the platform to live patient appointments:
- [ ] Set `DJANGO_DEBUG=False` in production `.env`.
- [ ] Generate a secure 64-character random string for `DJANGO_SECRET_KEY`.
- [ ] Configure live production PostgreSQL and Redis credentials.
- [ ] Configure live SendGrid/AWS SES credentials for `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`.
- [ ] Configure live Cloudinary production account credentials.
- [ ] Mount Let's Encrypt TLS certificate into Nginx and uncomment the SSL block in `nginx/nginx.conf`.
- [ ] Establish automated daily backups of `postgres_data` using the `pg_dump` command.
- [ ] Connect external uptime monitoring to `http://<domain>/health` and `http://<domain>/api/health/?detailed=1`.
