# Hospital Platform — Backend (Phases 9 - 18)

## 1. Overview & Purpose
This service provides the Django and Django REST Framework (DRF) backend for the EgleSora Hospital Platform project. 

- **Phase 9**: Foundation (PostgreSQL, Redis, Celery, SimpleJWT foundation, `/api/`, `/api/health/`)
- **Phase 10**: Domain Models (16 PostgreSQL models across Accounts, Hospital, Departments, Doctors, Scheduling, Appointments, Notifications)
- **Phase 11**: REST API Layer (DRF Serializers, ViewSets, URL routers, pagination, filtering, searching, ordering, validation)
- **Phase 12**: JWT Authentication + User Roles + RBAC (SimpleJWT with token blacklist, login, public registration restricted to `PATIENT`, token refresh, `/api/auth/me/`, logout/invalidation, reusable permission classes, object-level patient & staff data isolation)
- **Phase 13**: Real Appointment Booking + Availability + Concurrency Protection (Availability engine, deterministic slot generation, PostgreSQL row-level locking via `select_for_update()`, atomic transactions, double-booking prevention, cancellation, rescheduling, idempotency)
- **Phase 14**: Redis + Celery + Async Notifications (Message broker, asynchronous confirmation/cancellation/reschedule email dispatch, periodic Celery Beat appointment reminders, bounded retries with exponential backoff, transaction-safe execution via `transaction.on_commit()`, failure isolation)
- **Phase 15**: Cloudinary / Media Upload Integration (Production-ready media service, strict Pillow image validation, safe upload/replace/delete workflows, RBAC media management for doctors, facilities, profile logo, announcements, and departments)
- **Phase 16**: Comprehensive Testing + Security Hardening (Redis-backed rate limiting / throttling, production-grade exception sanitization, security headers, IDOR & object-level authorization hardening, PII/secret masking, 35-test dedicated security test suite, 198 total automated regression tests)
- **Phase 17**: Docker + Nginx + Gunicorn + Production Deployment (Containerization, Gunicorn WSGI, Nginx reverse proxy with client IP forwarding, health endpoints, Celery worker/beat services, 7-service Docker Compose stack, production runbook)
- **Phase 18**: Final Documentation, Quality Verification & Project Handoff (Final quality verification, documentation review, repository hygiene, production readiness evaluation, handoff runbook)

> **Note on Phase Boundaries:** Final Documentation, Quality Verification & Project Handoff (**Phase 18**) is COMPLETE. All project phases (Phases 0 through 18) are successfully completed and verified.

---

## 2. Technology Stack
- **Framework**: Django 5.1.x
- **API Engine**: Django REST Framework 3.17.x
- **Authentication Foundation**: djangorestframework-simplejwt 5.5.x
- **Database Driver**: PostgreSQL via `psycopg2-binary` 2.9.x
- **Cache & Message Broker**: Redis 8.x client
- **Asynchronous Processing**: Celery 5.6.x & `django-celery-beat` 2.9.x
- **Media Storage**: Cloudinary & `django-cloudinary-storage`
- **WSGI / Web Server**: Gunicorn 26.x
- **Testing**: Django test runner (`SimpleTestCase`) & Pytest

---

## 3. Environment Configuration
Configuration is strictly environment-driven via `.env` (template in `.env.example`). Never commit credentials or secrets to version control.

Key environment variables:
| Variable | Description | Default / Example |
|---|---|---|
| `DJANGO_SECRET_KEY` | Cryptographic signing secret | Set in `.env` |
| `DJANGO_DEBUG` | Enable debug mode | `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1,backend` |
| `POSTGRES_DB` / `DB_NAME` | PostgreSQL database name | `hospital_db` |
| `POSTGRES_USER` / `DB_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` / `DB_PASSWORD` | PostgreSQL password | Set in `.env` |
| `POSTGRES_HOST` / `DB_HOST` | PostgreSQL host | `localhost` / `postgres` |
| `POSTGRES_PORT` / `DB_PORT` | PostgreSQL port | `5432` |
| `CORS_ALLOWED_ORIGINS` | Explicit frontend allowed origins | `http://localhost:5173` |
| `REDIS_URL` | Redis cache and broker connection URL | `redis://localhost:6379/1` |
| `CELERY_BROKER_URL` | Celery task broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend URL | `redis://localhost:6379/0` |
| `JWT_ACCESS_MINUTES` | SimpleJWT access token lifetime | `60` |
| `JWT_REFRESH_DAYS` | SimpleJWT refresh token lifetime | `7` |
| `EMAIL_HOST` | SMTP server host | `localhost` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_USE_TLS` | Enable TLS for SMTP | `True` |
| `DEFAULT_FROM_EMAIL` | Default outbound email sender | `noreply@hospitalplatform.local` |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary storage account name | Set in `.env` |
| `CLOUDINARY_API_KEY` | Cloudinary API access key | Set in `.env` |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret | Set in `.env` |

---

## 4. Local Setup & Execution

### Virtual Environment Setup
```bash
# Create virtual environment using Python 3.12+ / 3.13
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r backend/requirements.txt
```

### Run Django System Checks
```bash
python backend/manage.py check
```

### Run Verification Tests
```bash
# Foundation verification tests
python tests/test_backend_foundation.py
python tests/test_foundation.py

# PostgreSQL Domain models & migration tests
python tests/test_domain_models.py

# REST API Layer tests
python tests/test_api_layer.py

# Phase 12 Authentication & RBAC tests
python tests/test_authentication_rbac.py

# Phase 13 Real Booking & Concurrency tests
python tests/test_appointment_booking.py

# Phase 14 Redis + Celery + Async Notifications tests
python tests/test_celery_notifications.py
```

### Run Celery Worker & Beat (Background Processing)
```bash
# Start Celery asynchronous worker
celery -A config worker --loglevel=info

# Start Celery Beat periodic scheduler (runs appointment reminder scanner)
celery -A config beat --loglevel=info
```

### Run Local Development Server
```bash
python backend/manage.py runserver 0.0.0.0:8000
```

---

## 5. Active Foundation & Domain Endpoints

### 1. API Root
- **Route**: `GET /api/`
- **Permissions**: `AllowAny`
- **Response**:
```json
{
  "service": "hospital-platform-api",
  "status": "active",
  "phase": "Phase 13 Booking & Concurrency",
  "version": "0.1.0",
  "endpoints": {
    "health": "http://localhost:8000/api/health/",
    "admin": "http://localhost:8000/admin/",
    "auth": "http://localhost:8000/api/auth/",
    "hospital": "http://localhost:8000/api/hospital/",
    "departments": "http://localhost:8000/api/departments/",
    "specialties": "http://localhost:8000/api/specialties/",
    "doctors": "http://localhost:8000/api/doctors/",
    "schedules": "http://localhost:8000/api/schedules/",
    "appointments": "http://localhost:8000/api/appointments/",
    "patients": "http://localhost:8000/api/patients/",
    "notifications": "http://localhost:8000/api/notifications/",
    "audit": "http://localhost:8000/api/audit/"
  },
  "message": "Hospital Platform REST API Layer operational."
}
```

### 2. Service Health Check
- **Route**: `GET /api/health/`
- **Permissions**: `AllowAny`
- **Description**: Lightweight probe decoupled from database connection to avoid fragile health checks in orchestration environments.
- **Response**:
```json
{
  "status": "ok",
  "service": "hospital-platform-api"
}
```

---

## 6. Authentication & RBAC (Phase 12)

The authentication system is built on Django REST Framework and SimpleJWT, with PostgreSQL database token blacklisting:

- `POST /api/auth/register/` — Public patient registration (hardcoded `PATIENT` role, creates `PatientProfile`)
- `POST /api/auth/login/` — Issues access + refresh JWTs, returns sanitized user profile
- `POST /api/auth/refresh/` — Rotates/issues new access token
- `GET /api/auth/me/` — Returns sanitized current authenticated user & patient profile summary
- `POST /api/auth/logout/` — Blacklists refresh token in PostgreSQL (`token_blacklist_blacklistedtoken`)

### Reusable Permissions (`apps.accounts.permissions`)
- `IsSuperAdmin`: Full system access
- `IsHospitalAdmin`: Administrative resource access
- `IsDoctorStaff`: Doctor operational data access
- `IsPatient`: Patient self-service access
- `IsAdminOrHospitalAdmin`: Platform administration
- `IsStaffOrAdmin`: Staff or administrator operations
- `IsAdminUserOrReadOnly`: Public `GET`, Admin-only mutations
- `IsPatientOwnerOrStaff`: Object-level ownership check (patients access own records; doctors access assigned patients; admins full access)

---

## 7. Real Booking & Concurrency Protection (Phase 13)

- **Availability Engine** (`apps.scheduling.services.AvailabilityEngine`): Computes deterministic slots evaluating doctor active status, weekly schedules, leave, overrides, shift bounds, recess breaks, timezone (`Asia/Kolkata`), and past slot cutoffs.
- **Transactional Booking Service** (`apps.appointments.services.AppointmentBookingService`):
  - Uses `transaction.atomic()`
  - PostgreSQL row-locking via `Doctor.objects.select_for_update()` to serialize simultaneous booking attempts
  - Re-evaluates slot capacity inside the transaction lock
  - Rejects overbooked slots with `409 Conflict`
- **Cancellation & Rescheduling**:
  - `POST /api/appointments/{reference}/cancel/`: Cancels consultation, sets cancellation reason/timestamp, releases slot.
  - `POST /api/appointments/{reference}/reschedule/`: Atomically validates target slot; rolls back if target is unavailable.
- **Idempotency Protection**: Supports `Idempotency-Key` header with database uniqueness to prevent duplicate creation on client network retries.

---

## 8. Redis, Celery & Asynchronous Architecture (Phase 14)
- **Redis Message Broker & Cache**:
  - Broker URL: `redis://localhost:6379/0` (in container: `redis://redis:6379/0`)
  - Result Backend: `redis://localhost:6379/0`
  - Cache: `redis://localhost:6379/1`
- **Asynchronous Tasks (`apps.notifications.tasks`)**:
  - `notifications.send_appointment_confirmation`: Dispatches booking confirmation email.
  - `notifications.send_appointment_cancellation`: Dispatches cancellation email with reason.
  - `notifications.send_appointment_reschedule`: Dispatches rescheduled appointment details.
  - `notifications.send_appointment_reminder`: Dispatches 24-hour reminder email.
  - `notifications.send_staff_alert`: Records `ADMIN_ALERT` notification for clinical oversight.
  - `reminders.process_appointment_reminders`: Celery Beat periodic task scanning upcoming confirmed appointments for tomorrow in `Asia/Kolkata` hospital timezone.
- **Transaction Safety**: All tasks are enqueued strictly via `transaction.on_commit()` after PostgreSQL atomic transactions commit. Aborted transactions never dispatch tasks.
- **Failure Isolation**: Gateway, network, or broker errors do NOT break clinical booking, cancellation, or rescheduling APIs.
- **Retry Policy & Exponential Backoff**: Tasks use `@shared_task(bind=True, max_retries=3)` with exponential backoff (`5 * 2^retries` seconds). Permanent failure records `status = 'FAILED'`, timestamp `failed_at`, and `error_message`.
- **Idempotency Protection**: Every notification event generates a unique PostgreSQL `idempotency_key` preventing duplicate email deliveries.

---

## 9. Cloudinary & Media Upload Architecture (Phase 15)

### Overview
Phase 15 integrates production-ready media handling using Cloudinary, Django REST Framework, and PostgreSQL. It replaces static/mock media placeholders with dynamic, secure cloud-hosted assets while maintaining strict RBAC, media validation, safe two-phase replacement, and credential masking.

### Supported Media Entities
- **Doctor Profile Photos** (`Doctor.photo` + `Doctor.image_public_id`): Publicly visible on doctor listings and details; managed via `/api/doctors/{id}/upload-photo/` and `/api/doctors/{id}/delete-photo/`.
- **Hospital Facility Photos** (`HospitalFacility.image` + `HospitalFacility.image_public_id`): Managed via `/api/facilities/{id}/upload-image/` and `/api/facilities/{id}/delete-image/`.
- **Hospital Profile Logo** (`HospitalProfile.logo` + `HospitalProfile.logo_public_id`): Managed via `/api/hospital/upload-logo/` and `/api/hospital/delete-logo/`.
- **Hospital Announcements** (`HospitalAnnouncement.image` + `HospitalAnnouncement.image_public_id`): Managed via `/api/announcements/{id}/upload-image/` and `/api/announcements/{id}/delete-image/`.
- **Department Images** (`Department.image` + `Department.image_public_id`): Managed via `/api/departments/{id}/upload-image/` and `/api/departments/{id}/delete-image/`.

### Configuration
Media handling is configured via environment variables:
```bash
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```
When variables are absent in local test environments, the service falls back gracefully without crashing, and mocked test suites execute without requiring live third-party connectivity.

### Cloudinary Folder Structure
Standardized folder names are used across domain entities:
- `hospital-platform/doctors/`: Doctor portrait photographs
- `hospital-platform/facilities/`: Facility and diagnostic ward imagery
- `hospital-platform/hospital/`: Institutional logos and header imagery
- `hospital-platform/announcements/`: Hospital notice and campaign banners
- `hospital-platform/departments/`: Clinical department representations

### Strict Media Validation
The centralized `MediaService.validate_image(file)` enforces:
1. **File Presence**: Rejects null or empty file submissions.
2. **Size Bounds**: Maximum allowed size is 5 MB (5,242,880 bytes).
3. **MIME Verification**: Supported content types: `image/jpeg`, `image/png`, `image/webp`. Rejects executable files, scripts, and arbitrary binary payloads.
4. **File Extension**: Permitted extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
5. **Binary Integrity Check**: Uses Pillow (`PIL.Image.open()`) to inspect image headers, verify image formats (`JPEG`, `PNG`, `WEBP`), and guarantee image readability. Corrupted or disguised files trigger HTTP 400 Bad Request.

### Two-Phase Safe Replacement Workflow
To avoid data loss if an upload or database operation fails:
1. Validate new image file.
2. Upload new asset to Cloudinary under a unique `public_id`.
3. Save the new URL and `image_public_id` to PostgreSQL within the model record.
4. Only upon successful database persistence, destroy the previous asset on Cloudinary.
5. If the upload or DB save fails, the previous asset and database reference remain completely intact.

### Safe Idempotent Deletion
- Deleting an asset removes the Cloudinary asset via `cloudinary.uploader.destroy()` and clears the model fields (`image=None`, `image_public_id=None`).
- Deleting when no asset exists or repeated deletion requests succeed cleanly without corrupting the domain model.

### Authorization & RBAC
- **Public & Patients**: Can view public media URLs (`photo_url`, `image_url`, `logo_url`) through GET endpoints, but cannot upload, replace, or delete media (returns HTTP 401 Unauthorized or HTTP 403 Forbidden).
- **Hospital Admin & Super Admin**: Possess full permissions across all hospital media endpoints.
- **Doctor Staff**: Object-level permissions allow doctors to upload, replace, or delete only their own profile photo (`CanManageDoctorMedia`). Doctor staff cannot alter other doctors' photos or hospital facility assets.

### Failure Isolation & Credential Safety
- Cloudinary errors return clean HTTP 500 error responses: `{"error": "Failed to upload image. Please try again later."}`.
- Internal stack traces, API keys, or API secrets are **NEVER** returned in API responses or written to production logs.

### Media Test Suite
Run the 30 dedicated Phase 15 automated tests:
```bash
python tests/test_cloudinary_media.py
```

---

## 10. Comprehensive Security Hardening & Rate Limiting (Phase 16)

### Overview
Phase 16 executes a thorough security hardening pass across the entire Hospital Platform, verifying authentication security, role isolation, object authorization, rate limiting, and failure containment without introducing unnecessary architecture bloat.

### Redis-Backed Rate Limiting (`backend/config/throttling.py`)
Sensitive and abuse-prone endpoints are protected with DRF throttles backed by Redis cache:
- **Login** (`LoginRateThrottle`): 5 attempts per minute per IP address.
- **Registration** (`RegisterRateThrottle`): 3 registrations per minute per IP address.
- **Token Refresh** (`TokenRefreshRateThrottle`): 10 refreshes per minute per IP address.
- **Appointment Booking** (`AppointmentBookingRateThrottle`): 10 bookings per minute per user/IP address.
- **Media Upload** (`MediaUploadRateThrottle`): 10 uploads per minute per user.
- Throttled requests immediately return HTTP 429 Too Many Requests with informative retry-after headers.

### Production Exception Sanitization (`backend/config/exceptions.py`)
- In production mode (`DEBUG=False`), unhandled exceptions return a sanitized JSON payload:
  `{"detail": "An internal server error occurred. Please contact hospital support."}`
- Tracebacks, file paths, database connection strings, and credential secrets (`CLOUDINARY_API_SECRET`, `SECRET_KEY`) are masked and never exposed to the client.

### Security Headers Configured (`backend/config/settings.py`)
- `X_FRAME_OPTIONS = 'DENY'`: Clickjacking prevention.
- `SECURE_CONTENT_TYPE_NOSNIFF = True`: MIME-sniffing protection.
- `SECURE_REFERRER_POLICY = 'same-origin'`: Restricts sensitive referrer leakage.
- `SESSION_COOKIE_HTTPONLY = True` & `CSRF_COOKIE_HTTPONLY = True`: Blocks XSS cookie theft.
- `CORS_ALLOW_ALL_ORIGINS = False`: Production CORS strictly requires explicit origins.
- Production HTTPS flags (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`) are environment-driven.

### Object-Level Authorization & IDOR Protection
- Patients can only query and mutate their own appointments, profiles, and notifications. Querying another patient's appointment returns HTTP 404 (preventing ID enumeration) or HTTP 403.
- Doctor staff members are restricted to their own doctor profile and cannot alter colleagues' records.
- Administrative mutation endpoints strictly require `HOSPITAL_ADMIN` or `SUPER_ADMIN` roles.

### Security Test Suite
Run the 35 dedicated Phase 16 automated tests:
```bash
python tests/test_security_hardening.py
```

