# Hospital Platform — Comprehensive Testing Strategy & Verification Guide

## Provenance: Phase 0 Foundation → Phase 18 Final Quality Verification

This document outlines the testing architecture, quality assurance methodology, security test suites, and regression verification protocols for the Eagle Sora Hospital Platform.

---

## 1. Test Architecture Overview

All backend tests execute against a **live PostgreSQL instance** (`hospital_db`) and **live Redis instance** (`localhost:6379`), reflecting real production database concurrency, row-level locks, constraints, and cache structures. No SQLite fallback is ever used.

The test suite is organized into 9 specialized test modules:

| Test Module | Coverage Domain | Key Verifications | Test Count |
|---|---|---|---|
| `tests/test_foundation.py` | Architecture & Infrastructure | Directory layout, configs, Docker, Nginx, .env templates | 7 |
| `tests/test_backend_foundation.py` | Django Core & App Health | Core settings, DB engine, Redis, Celery, SimpleJWT, /api/health/ | 11 |
| `tests/test_domain_models.py` | Domain Integrity & Validation | 16 PostgreSQL models, clean() constraints, slug generation | 23 |
| `tests/test_api_layer.py` | REST API Layer & Serialization | ViewSets, routers, pagination, filtering, search, ordering | 21 |
| `tests/test_authentication_rbac.py` | Auth & Access Control | JWT lifecycle, blacklist, role isolation, unprivileged registration | 24 |
| `tests/test_appointment_booking.py` | Booking & Concurrency Engine | Real multithreaded concurrency, row locks, idempotency, lifecycle | 30 |
| `tests/test_celery_notifications.py` | Background Tasks & Celery Beat | Async dispatch, idempotency, retry backoff, failure isolation | 17 |
| `tests/test_cloudinary_media.py` | Media Upload & Validation | Pillow binary check, 5MB limit, replacement safety, RBAC | 30 |
| `tests/test_security_hardening.py` | Enterprise Security Hardening | Rate limiting, IDOR, SQLi/XSS resilience, header verification | 35 |
| **Total Test Count** | **Full System Regression Suite** | **All Clinical & Security Requirements Verified** | **198 Tests** |

---

## 2. Running Test Suites

### 2.1 Complete Test Suite Execution

Run all test suites sequentially using the virtual environment:

```powershell
# Foundation and architecture tests
.venv\Scripts\python.exe tests/test_foundation.py
.venv\Scripts\python.exe tests/test_backend_foundation.py

# Domain model logic and constraint tests
.venv\Scripts\python.exe tests/test_domain_models.py

# REST API layer tests
.venv\Scripts\python.exe tests/test_api_layer.py

# Authentication, JWT, and Role-Based Access Control tests
.venv\Scripts\python.exe tests/test_authentication_rbac.py

# Appointment booking, availability, and multithreaded concurrency tests
.venv\Scripts\python.exe tests/test_appointment_booking.py

# Celery async notification and task failure isolation tests
.venv\Scripts\python.exe tests/test_celery_notifications.py

# Cloudinary media upload, validation, and safe replacement tests
.venv\Scripts\python.exe tests/test_cloudinary_media.py

# Phase 16 Comprehensive Security Hardening & Rate Limiting tests
.venv\Scripts\python.exe tests/test_security_hardening.py
```

### 2.2 Running with Django Test Runner

You can also run all tests or individual test suites directly through `manage.py`:

```powershell
# Run the complete test suite
.venv\Scripts\python.exe backend/manage.py test tests

# Run only security hardening tests
.venv\Scripts\python.exe backend/manage.py test tests.test_security_hardening

# Run only appointment booking tests
.venv\Scripts\python.exe backend/manage.py test tests.test_appointment_booking
```

---

## 3. Security Hardening Test Suite (`test_security_hardening.py`)

The Phase 16 security suite implements 35 explicit verification tests covering:

### 3.1 Authentication Security
- **Anonymous Access Rejection**: Confirms anonymous requests to protected endpoints return `401 Unauthorized`.
- **Expired Token Handling**: Verifies expired tokens are rejected.
- **Malformed & Forged Token Handling**: Confirms tamper-evident token rejection.
- **Refresh Token Blacklisting**: Confirms blacklisted refresh tokens cannot generate new access tokens.
- **Privilege Escalation Prevention**: Confirms registration payload cannot assign administrative roles (`SUPER_ADMIN`, `HOSPITAL_ADMIN`, `DOCTOR_STAFF`).

### 3.2 Role-Based Access Control (RBAC)
- **Patient Admin Shield**: Verifies `PATIENT` role receives `403 Forbidden` on all administrative mutation endpoints.
- **Doctor Staff Scope**: Verifies `DOCTOR_STAFF` cannot mutate hospital profile or institution-level content.
- **Audit Log Isolation**: Verifies non-administrative users cannot query audit records.

### 3.3 Object-Level Authorization & IDOR
- **Appointment Cross-Access**: Verifies Patient A cannot view, cancel, or reschedule Patient B's appointment (returning `404 Not Found` or `403 Forbidden`).
- **Profile Cross-Access**: Verifies Patient A cannot view Patient B's profile via direct ID manipulation.
- **Notification Cross-Access**: Verifies Patient A cannot access Patient B's notifications.
- **Doctor Photo Mutation**: Verifies Doctor Staff 1 cannot upload photos for Doctor 2.

### 3.4 Input Validation & Injection Resistance
- **Malformed Payloads**: Confirms invalid JSON and non-numeric values return clean `400 Bad Request`.
- **Date/Time Validation**: Confirms non-existent calendar dates and impossible times return clean `400 Bad Request`.
- **SQL Injection Resistance**: Submits malicious SQL strings (`' OR 1=1 --`, `UNION SELECT`) into search and filter parameters, confirming safe Django ORM parameterization with zero tracebacks.
- **XSS Payload Sanitization**: Submits `<script>alert('x')</script>` in text fields, verifying plain-text storage without executable execution.

### 3.5 Rate Limiting / Throttling
- **Login Throttling**: Verifies repeated rapid authentication attempts trigger `429 Too Many Requests`.
- **Appointment Creation Throttling**: Verifies rapid appointment creation triggers `429 Too Many Requests`.

### 3.6 Media Upload Security
- **Pillow Binary Verification**: Confirms executable scripts or text files renamed to `.jpg` are caught and rejected.
- **Oversized File Rejection**: Confirms files exceeding 5MB are rejected with `400 Bad Request`.
- **RBAC Upload Enforcement**: Confirms unauthorized users receive `403 Forbidden` on upload endpoints.
- **Secret Masking**: Confirms Cloudinary errors never leak `CLOUDINARY_API_SECRET` into API responses.

### 3.7 Secrets, Privacy & Error Sanitization
- **Credential Masking**: Confirms user serializer responses never output password hashes.
- **Production Error Sanitization**: Confirms that when `DEBUG=False`, unhandled 500 exceptions return generic error messages without database connection strings or stack traces.
- **Security Headers**: Verifies `X-Frame-Options: DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`, and `SECURE_REFERRER_POLICY` in HTTP responses.

---

## 4. Concurrency & Integrity Testing

The booking engine is subjected to true concurrent booking attempts in `test_appointment_booking.py` (`test_22_concurrent_booking_test`):
- Multiple operating system threads simulate simultaneous booking requests for the exact same doctor, date, and 30-minute time slot.
- Uses PostgreSQL row-level locking (`select_for_update()`) inside an atomic transaction.
- **Verification Guarantee**: Exactly one request succeeds with `201 Created`; all competing concurrent requests receive `409 Conflict`. Exactly one appointment row exists in PostgreSQL.

---

## 5. Frontend Build Verification

To verify that frontend assets compile without syntax, bundling, or styling errors:

```powershell
cd frontend
npm run build
```

**Result**: Vite production bundle completes cleanly with zero errors.

---

## 6. Running Tests in Containerized Environment

When the Docker Compose stack is running, tests can also be executed inside the running `backend` container:

```bash
# Execute full test suite inside container
docker compose exec backend python manage.py test tests

# Check Django system integrity
docker compose exec backend python manage.py check

# Check migration status
docker compose exec backend python manage.py showmigrations
```

---

## 7. External Service Boundaries & Test Environment Limitations

1. **Transactional Email / SMTP**: Tests use mock mail backends (`locmem`) and simulated network failure exceptions (`SMTPException`) to verify async task queues, retries, and failure isolation without sending live external emails.
2. **Cloudinary Media Storage**: Tests use mocked Cloudinary uploader/destroyer wrappers to verify image validation, safe replacement, and DB synchronization without calling live third-party cloud endpoints.
3. **External HTTPS / SSL**: SSL redirect settings are disabled in local testing environments (`DJANGO_SECURE_SSL_REDIRECT=False`) so HTTP test runners can execute unhindered. Production TLS termination is handled at Nginx.
