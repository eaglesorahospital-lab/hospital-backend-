# API Specification & Reference Documentation

## Provenance: Phase 0 Foundation (Initial) → Phase 11 REST API Layer → Phase 12 Auth & RBAC → Phase 13 Real Booking & Concurrency → Phase 14 Celery & Notifications → Phase 15 Cloudinary Media Upload → Phase 16 Security Hardening & Testing

This document provides the complete RESTful API specification for the Eagle Sora Hospital Platform backend.

> [!NOTE]
> **Phase 16 Comprehensive Testing & Security Hardening Status**:
> In Phase 16, enterprise security hardening is fully active:
> - **Redis-Backed Rate Limiting**: Abuse-sensitive endpoints are throttled (`429 Too Many Requests`).
> - **Sanitized Exception Handling**: In production mode (`DEBUG=False`), unhandled exceptions return sanitized 500 responses without tracebacks or leaked secrets.
> - **Security Headers**: All API responses enforce `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: same-origin`.
> - **Object-Level Authorization & IDOR Protection**: Direct object access strictly checks caller identity and ownership.
> - **Cloudinary Secret Masking**: Credentials and API secrets are never returned in error messages or serializer payloads.

---

## 1. Global API Standards

- **Base URL Namespace**: `/api/`
- **Wire Format**: JSON (`application/json`)
- **Default Pagination**: Page-number pagination (`StandardResultsSetPagination`)
  - Default Page Size: 10 items
  - Query Parameter: `?page=X&page_size=Y` (max `page_size`: 100)
  - Envelope Format:
    ```json
    {
      "count": 42,
      "next": "http://localhost:8000/api/doctors/?page=2",
      "previous": null,
      "results": [...]
    }
    ```
- **Rate Limiting (HTTP 429 Too Many Requests)**:
  - Login (`/api/auth/login/`): `5/minute` (IP-based)
  - Register (`/api/auth/register/`): `3/minute` (IP-based)
  - Token Refresh (`/api/auth/refresh/`): `10/minute` (IP-based)
  - Appointment Booking (`/api/appointments/` POST): `10/minute` (User/IP-based)
  - Media Upload (`/api/doctors/{id}/upload-photo/`, etc.): `10/minute` (User-based)
  - Response Format:
    ```json
    {
      "detail": "Request was throttled. Expected available in 58 seconds."
    }
    ```
- **Global Error Format**:
  - Validation Errors (400 Bad Request):
    ```json
    {
      "field_name": ["Specific validation error message."]
    }
    ```
  - Authentication Errors (401 Unauthorized):
    ```json
    {
      "detail": "Given token not valid for any token type"
    }
    ```
  - Permission Errors (403 Forbidden):
    ```json
    {
      "detail": "You do not have permission to perform this action."
    }
    ```
  - Not Found Errors (404 Not Found):
    ```json
    {
      "detail": "Not found."
    }
    ```
  - Slot Conflict / Double-Booking (409 Conflict):
    ```json
    {
      "detail": "Requested slot overlaps with doctor scheduled break (Lunch Break: 13:00 - 14:00)."
    }
    ```
  - Method Not Allowed (405 Method Not Allowed):
    ```json
    {
      "detail": "Method \"POST\" not allowed."
    }
    ```
  - Internal Server Error (500 Internal Server Error, sanitized in production):
    ```json
    {
      "detail": "An internal server error occurred. Please contact hospital support."
    }
    ```

---

## 2. API Endpoints Directory

### 2.1 Core Infrastructure
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/` | API Root service status & directory of endpoints | None |
| `GET` | `/api/health/` | Service health check for load balancers & orchestrators | None |

#### Sample Response: `GET /api/`
```json
{
  "service": "hospital-platform-api",
  "status": "active",
  "phase": "Phase 12 JWT Authentication & RBAC",
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

---

### 2.2 Authentication & Authorization (`/api/auth/`)

JWT authentication and Role-Based Access Control (RBAC) are powered by `djangorestframework-simplejwt` with database token blacklisting.

#### Endpoints Summary
| Method | Endpoint | Description | Auth Required | Permissions |
|---|---|---|---|---|
| `POST` | `/api/auth/register/` | Register new patient account & profile | No | `AllowAny` (Creates `PATIENT` only) |
| `POST` | `/api/auth/login/` | Authenticate user & issue JWT token pair | No | `AllowAny` |
| `POST` | `/api/auth/refresh/` | Obtain a new access token via refresh token | No | `AllowAny` |
| `GET` | `/api/auth/me/` | Current authenticated user profile & details | Yes | `IsAuthenticated` |
| `POST` | `/api/auth/logout/` | Invalidate/blacklist refresh token | Yes | `IsAuthenticated` |

---

#### 1. Registration (`POST /api/auth/register/`)
Public registration strictly defaults role to `PATIENT`. Privileged roles (`SUPER_ADMIN`, `HOSPITAL_ADMIN`, `DOCTOR_STAFF`) cannot be chosen via registration. Automatically creates linked `PatientProfile`.

- **Request Body**:
```json
{
  "email": "jane.doe@example.com",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "first_name": "Jane",
  "last_name": "Doe",
  "date_of_birth": "1992-06-15",
  "gender": "FEMALE",
  "phone": "+1-555-0199",
  "blood_group": "A+"
}
```

- **Validation Rules**:
  - `email`: Must be unique, valid email format.
  - `password`: Enforces Django password validators (min length, non-numeric, not common).
  - `password_confirm`: Must match `password` exactly.
  - `role`: Hardcoded to `PATIENT`; client input cannot alter role.

- **Success Response (`201 Created`)**:
```json
{
  "id": 4,
  "email": "jane.doe@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "role": "PATIENT",
  "is_active": true,
  "date_joined": "2026-10-08T20:00:00Z",
  "patient_profile": {
    "id": 4,
    "mrn": "MRN-2026-XXXXXX",
    "gender": "FEMALE",
    "blood_group": "A+",
    "date_of_birth": "1992-06-15",
    "phone": "+1-555-0199"
  }
}
```

---

#### 2. Login (`POST /api/auth/login/`)
Authenticates email and password credentials. Does not reveal whether an email exists on invalid attempts.

- **Request Body**:
```json
{
  "email": "patient@example.com",
  "password": "PatientPassword123!"
}
```

- **Success Response (`200 OK`)**:
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 2,
    "email": "patient@example.com",
    "name": "Jane Patient",
    "role": "PATIENT"
  }
}
```

- **Invalid Credentials Response (`400 Bad Request`)**:
```json
{
  "detail": ["Invalid email or password."]
}
```

---

#### 3. Token Refresh (`POST /api/auth/refresh/`)
Exchanges an active refresh token for a newly signed access token.

- **Request Body**:
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

- **Success Response (`200 OK`)**:
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

- **Invalid / Expired / Blacklisted Token Response (`401 Unauthorized`)**:
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

---

#### 4. Current User (`GET /api/auth/me/`)
Requires `Authorization: Bearer <access_token>` header. Returns sanitized authenticated user record and patient profile summary if present. Never returns passwords or password hashes.

- **Success Response (`200 OK`)**:
```json
{
  "id": 2,
  "email": "patient@example.com",
  "first_name": "Jane",
  "last_name": "Patient",
  "role": "PATIENT",
  "is_active": true,
  "date_joined": "2026-10-08T19:30:00Z",
  "patient_profile": {
    "id": 1,
    "mrn": "MRN-2026-000001",
    "gender": "FEMALE",
    "blood_group": "A+",
    "date_of_birth": "1992-06-15",
    "phone": "+1-555-0199"
  }
}
```

- **Unauthenticated Response (`401 Unauthorized`)**:
```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

#### 5. Logout & Invalidation (`POST /api/auth/logout/`)
Requires authentication. Adds the supplied refresh token to the database blacklist table (`token_blacklist_blacklistedtoken`), rendering it permanently invalid.

- **Request Headers**: `Authorization: Bearer <access_token>`
- **Request Body**:
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

- **Success Response (`200 OK`)**:
```json
{
  "detail": "Successfully logged out. Refresh token invalidated."
}
```

---

#### 6. Role Matrix & RBAC Authorization Policy

| Endpoint / Resource | Public (Anon) | PATIENT | DOCTOR_STAFF | HOSPITAL_ADMIN | SUPER_ADMIN |
|---|---|---|---|---|---|
| Catalog (`/api/hospital/`, `/api/departments/`, `/api/doctors/`, `/api/specialties/`) | `GET` (Read-Only) | `GET` (Read-Only) | `GET` (Read-Only) | `GET`, `POST`, `PATCH`, `DELETE` | `GET`, `POST`, `PATCH`, `DELETE` |
| Doctor Schedules (`/api/schedules/`) | `GET` (Read-Only) | `GET` (Read-Only) | `GET`, `POST` (own), `PATCH` (own) | Full CRUD | Full CRUD |
| Schedule Leaves/Overrides | Forbidden | Forbidden | `GET`, `POST` (own), `PATCH` (own) | Full CRUD | Full CRUD |
| Appointments (`/api/appointments/`) | Forbidden | `GET` (own only), `POST` (book), `PATCH` (own only) | `GET` (assigned only), `PATCH` (status) | Full CRUD | Full CRUD |
| Patient Profiles (`/api/patients/`) | Forbidden | `GET` (own only), `PATCH` (own only) | `GET` (clinical context), `PATCH` | Full CRUD | Full CRUD |
| Notifications (`/api/notifications/`) | Forbidden | `GET` (own recipient) | `GET` (own recipient) | Full CRUD | Full CRUD |
| Audit Trail (`/api/audit/`) | Forbidden | Forbidden | Forbidden | `GET` (Read-Only) | `GET` (Read-Only) |

---

#### 7. Object-Level Access Enforcement
- **Patient Isolation**: Patients are scoped strictly to their own records. Querying `/api/appointments/` or `/api/patients/` automatically filters the queryset by `request.user`. Attempting to retrieve another patient's appointment by reference returns `404 Not Found` (preventing ID enumeration / private data leakage).
- **Audit Logs**: Completely inaccessible to patients and unprivileged staff. Mutating audit records is rejected with `405 Method Not Allowed` across all roles.

---

#### 8. Standard Error Responses
- **401 Unauthorized (Missing or Invalid Token)**:
```json
{
  "detail": "Authentication credentials were not provided."
}
```
- **403 Forbidden (Insufficient Role Privileges)**:
```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

### 2.3 Hospital Institutional Information (`/api/hospital/`)
| Method | Endpoint | Description | Query Parameters / Actions |
|---|---|---|---|
| `GET` | `/api/hospital/` | List hospital profiles | None |
| `GET` | `/api/hospital/current/` | Primary active hospital profile | None |
| `GET` | `/api/hospital/facilities/` | List clinical facilities | `?is_active=true&search=ICU&ordering=order` |
| `GET` | `/api/hospital/announcements/` | Public hospital news & advisories | `?category=Advisory&search=OPD&ordering=-published_at` |
| `GET` | `/api/hospital/announcements/{slug}/` | Announcement details by slug | None |
| `GET` | `/api/hospital/faqs/` | General patient guidance FAQs | `?search=visiting&ordering=order` |

---

### 2.3 Departments (`/api/departments/`)
| Method | Endpoint | Description | Query Parameters / Actions |
|---|---|---|---|
| `GET` | `/api/departments/` | List clinical departments | `?is_active=true&specialty=Cardio&search=Heart&ordering=name` |
| `GET` | `/api/departments/{slug}/` | Department details by slug | None |
| `GET` | `/api/departments/{slug}/services/` | Active services of a department | None |
| `GET` | `/api/departments/{slug}/faqs/` | Active FAQs of a department | None |

#### Sample Response: `GET /api/departments/cardiology/`
```json
{
  "id": 1,
  "name": "Cardiology",
  "slug": "cardiology",
  "specialty": "Cardiovascular Sciences",
  "short_description": "Heart and vascular care.",
  "full_description": "Comprehensive cardiac surgery and intervention.",
  "opd_hours": "Mon - Sat: 09:00 AM - 04:00 PM",
  "location": "Wing B, 2nd Floor",
  "contact_phone": "+91 22 0000 2233",
  "contact_email": "cardio@eglesora.org",
  "extension": "204",
  "is_active": true,
  "services": [
    {
      "id": 1,
      "department": 1,
      "name": "Echocardiography",
      "description": "Diagnostic ultrasound of the heart.",
      "order": 1,
      "is_active": true
    }
  ],
  "faqs": [
    {
      "id": 1,
      "department": 1,
      "question": "Is fasting required for Echo?",
      "answer": "No, fasting is not required.",
      "order": 1,
      "is_active": true
    }
  ],
  "created_at": "2026-10-08T19:30:00Z",
  "updated_at": "2026-10-08T19:30:00Z"
}
```

---

### 2.4 Clinical Specialties (`/api/specialties/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/specialties/` | List medical specialties | `?is_active=true&search=Neuro&ordering=name` |
| `GET` | `/api/specialties/{slug}/` | Specialty details by slug | None |

---

### 2.5 Consultant Doctors (`/api/doctors/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/doctors/` | List active doctors | `?department={id}&department__slug={slug}&specialty={id}&specialty__slug={slug}&consultation_type={type}&search={query}&ordering={field}` |
| `GET` | `/api/doctors/{slug}/` | Consultant doctor profile by slug | None |

#### Sample Response: `GET /api/doctors/dr-marcus-vance/`
```json
{
  "id": 1,
  "name": "Dr. Marcus Vance",
  "slug": "dr-marcus-vance",
  "department": 1,
  "department_detail": {
    "id": 1,
    "name": "Cardiology",
    "slug": "cardiology",
    "location": "Wing B, 2nd Floor",
    "opd_hours": "Mon - Sat: 09:00 AM - 04:00 PM"
  },
  "specialty": 1,
  "specialty_detail": {
    "id": 1,
    "name": "Interventional Cardiology",
    "slug": "interventional-cardiology"
  },
  "specialty_name": "Interventional Cardiology",
  "qualification": "MD, DM (Cardiology)",
  "experience_years": 14,
  "bio": "Senior consultant in interventional cardiology.",
  "expertise": "Coronary angioplasty, TAVI",
  "consultation_type": "In-person Consultation",
  "consultation_duration_minutes": 30,
  "consultation_location": "Wing B, Suite 204",
  "image": null,
  "is_active": true,
  "created_at": "2026-10-08T19:30:00Z",
  "updated_at": "2026-10-08T19:30:00Z"
}
```

---

### 2.6 Scheduling Domain (`/api/schedules/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/schedules/` | List weekly doctor shift templates | `?doctor={id}&doctor__slug={slug}&day_of_week={day}&is_working_day=true` |
| `GET` | `/api/schedules/{id}/` | Schedule shift details | None |
| `GET` | `/api/schedules/leaves/` | Doctor planned absences | `?doctor={id}&doctor__slug={slug}&is_active=true` |
| `GET` | `/api/schedules/overrides/` | Date-specific shift overrides | `?doctor={id}&doctor__slug={slug}&override_date={YYYY-MM-DD}&is_available=true` |
| `GET` | `/api/schedules/availability/` | Query doctor slot availability | `?doctor={id}&date={YYYY-MM-DD}` |
| `GET` | `/api/doctors/{slug}/availability/` | Direct doctor availability endpoint | `?date={YYYY-MM-DD}` |

#### Sample Availability Response (`GET /api/doctors/dr-sarah-jenkins/availability/?date=2026-10-15`):
```json
{
  "doctor": {
    "id": 1,
    "name": "Dr. Sarah Jenkins",
    "slug": "dr-sarah-jenkins"
  },
  "date": "2026-10-15",
  "timezone": "Asia/Kolkata",
  "slot_duration_minutes": 30,
  "capacity_per_slot": 1,
  "available_slots": [
    {
      "start_time": "09:00:00",
      "end_time": "09:30:00",
      "available": true
    },
    {
      "start_time": "12:00:00",
      "end_time": "12:30:00",
      "available": false
    }
  ]
}
```

---

### 2.7 Appointments Domain (`/api/appointments/`)
| Method | Endpoint | Description | Query Parameters / Payload |
|---|---|---|---|
| `GET` | `/api/appointments/` | List consultations (Scoped by role) | `?status={STATUS}&doctor={id}&patient={id}&appointment_date={YYYY-MM-DD}` |
| `GET` | `/api/appointments/{reference}/` | Consultation details by reference | None |
| `POST` | `/api/appointments/` | Transactional slot booking with row locking | JSON Body (see schema below) |
| `POST` | `/api/appointments/{reference}/cancel/` | Cancel consultation & release slot | JSON Body (`reason`) |
| `POST` | `/api/appointments/{reference}/reschedule/` | Atomic reschedule to target slot | JSON Body (`appointment_date`, `start_time`, `end_time`) |
| `PATCH` | `/api/appointments/{reference}/` | Update status (validated lifecycle) | JSON Body (`status`, `notes`) |
| `DELETE` | `/api/appointments/{reference}/` | Remove consultation record | None |

#### 1. Appointment Booking Payload (`POST /api/appointments/`):
- **Headers**:
  - `Authorization: Bearer <access_token>`
  - `Idempotency-Key: <unique-uuid>` *(Optional: prevents duplicate charges or double bookings on client retries)*
- **Body**:
```json
{
  "doctor": 1,
  "appointment_date": "2026-11-15",
  "start_time": "10:00:00",
  "end_time": "10:30:00",
  "appointment_type": "IN_PERSON",
  "reason_for_visit": "Routine hypertension checkup.",
  "notes": "Patient requested morning slot."
}
```

#### 2. Concurrency & Double-Booking Protection:
- All bookings execute inside a PostgreSQL `transaction.atomic()` block.
- Locks the consultant row using `Doctor.objects.select_for_update()`, serializing concurrent booking attempts for that doctor.
- Re-validates doctor active status, leave dates, schedule overrides, working shift bounds, and break overlaps.
- Checks active appointments against `DoctorSchedule.capacity`.
- If the slot is already booked to capacity:
  - **HTTP 409 Conflict**:
    ```json
    {
      "detail": "The selected appointment slot is no longer available."
    }
    ```

#### 3. Cancellation (`POST /api/appointments/{reference}/cancel/`):
- **Body**:
```json
{
  "reason": "Family emergency; rescheduling later."
}
```
- Sets `status = CANCELLED`, records `cancelled_at` timestamp and rationale.
- Releases the time slot so other patients can immediately book it.

#### 4. Rescheduling (`POST /api/appointments/{reference}/reschedule/`):
- **Body**:
```json
{
  "appointment_date": "2026-11-18",
  "start_time": "11:00:00",
  "end_time": "11:30:00",
  "reason": "Prefer weekday morning."
}
```
- Atomically validates the target slot.
- If target slot is full or invalid, the entire transaction rolls back; the original appointment remains untouched.
- On success: marks original appointment as `RESCHEDULED`, creates new appointment linked via `rescheduled_from`.

#### 5. Lifecycle Transitions:
- Allowed:
  - `REQUESTED` → `CONFIRMED`, `CANCELLED`
  - `CONFIRMED` → `CHECKED_IN`, `CANCELLED`, `NO_SHOW`, `RESCHEDULED`
  - `CHECKED_IN` → `COMPLETED`, `CANCELLED`
- Terminal states: `COMPLETED`, `CANCELLED`, `NO_SHOW`, `RESCHEDULED` (no further transitions permitted).
- Disallowed transitions return `400 Bad Request`.

---

### 2.8 Patients Domain (`/api/patients/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/patients/` | List patient demographic records | `?gender={MALE/FEMALE}&blood_group={B+}&is_active=true&search={query}` |
| `GET` | `/api/patients/{id}/` | Patient demographics by ID | None |
| `POST` | `/api/patients/` | Register patient profile | JSON Body (demographics) |
| `PATCH` | `/api/patients/{id}/` | Update patient profile | JSON Body |

---

### 2.9 Notifications Domain (`/api/notifications/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/notifications/` | Outbound communication dispatch logs | `?notification_type={TYPE}&channel={EMAIL/SMS}&status={SENT}&appointment={id}&search={recipient}` |
| `GET` | `/api/notifications/{id}/` | Notification details | None |

#### 1. Notification Model & Payload Schema:
```json
{
  "id": 1,
  "recipient": "patient@example.com",
  "recipient_user": 5,
  "appointment": 12,
  "appointment_reference": "APT-2026-X1Y2Z3",
  "notification_type": "APPOINTMENT_CONFIRMATION",
  "channel": "EMAIL",
  "status": "SENT",
  "subject": "[Eagle Sora Hospital] Appointment Confirmed - APT-2026-X1Y2Z3",
  "message": "Dear Patient, your appointment at Eagle Sora Hospital has been successfully confirmed...",
  "provider_reference": "smtp-a1b2c3d4e5f6",
  "retry_count": 0,
  "error_message": "",
  "idempotency_key": "CONFIRM_12",
  "sent_at": "2026-10-08T18:00:00Z",
  "failed_at": null,
  "created_at": "2026-10-08T17:59:58Z",
  "updated_at": "2026-10-08T18:00:00Z"
}
```

#### 2. Asynchronous Architecture (Redis + Celery + Beat):
- **Broker & Result Backend**: Redis 7 running on `redis://localhost:6379/0` (container: `redis://redis:6379/0`).
- **Post-Transaction Task Dispatch**: Asynchronous tasks are scheduled exclusively via `transaction.on_commit()` after the PostgreSQL transaction successfully commits. If the booking transaction rolls back, zero notification tasks are queued.
- **Failure Isolation**: Notification delivery failures (SMTP network timeout, authentication failure, Redis unavailability) do **NOT** fail or roll back the clinical appointment creation, cancellation, or rescheduling operations.
- **Bounded Retries & Exponential Backoff**: Tasks use Celery `@shared_task(bind=True, max_retries=3)`. Temporary failures trigger exponential backoff countdowns (`5 * 2^retries` seconds). Permanent exhaustion records `status = 'FAILED'`, sets `failed_at`, and captures `error_message`.
- **Idempotency Protection**: Every notification event generates a unique PostgreSQL `idempotency_key` (e.g. `CONFIRM_{apt_id}`, `CANCEL_{apt_id}`, `RESCHEDULE_{apt_id}`). Duplicate task deliveries check existing status and exit cleanly without duplicate emails.
- **Periodic Reminders (Celery Beat)**: Periodic task `reminders.process_appointment_reminders` runs every 30 minutes to scan upcoming confirmed appointments for tomorrow in `Asia/Kolkata` hospital timezone and dispatches reminders idempotently.

---

### 2.11 Audit Trail (`/api/audit/`)
| Method | Endpoint | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/audit/` | Activity audit trail logs (**Strictly Read-Only**) | `?action={ACTION}&resource_type={TYPE}&result={SUCCESS}&search={actor}&ordering=-timestamp` |
| `GET` | `/api/audit/{id}/` | Audit log entry details | None |

> [!NOTE]
> `POST`, `PUT`, `PATCH`, and `DELETE` requests to `/api/audit/` return `405 Method Not Allowed`. Audit trails are immutable.

---

### 2.12 Media Management Endpoints (`/api/doctors/`, `/api/facilities/`, `/api/hospital/`, `/api/announcements/`, `/api/departments/`)

Dedicated multipart/form-data upload and deletion actions are provided for each media-bearing domain entity:

| Method | Endpoint | Description | Content-Type | Auth / RBAC |
|---|---|---|---|---|
| `POST` | `/api/doctors/{id}/upload-photo/` | Upload or replace doctor portrait photo | `multipart/form-data` | `IsHospitalAdmin`, `IsSuperAdmin`, or `CanManageDoctorMedia` (own profile) |
| `DELETE` | `/api/doctors/{id}/delete-photo/` | Delete doctor photo & remove Cloudinary asset | None | `IsHospitalAdmin`, `IsSuperAdmin`, or `CanManageDoctorMedia` (own profile) |
| `POST` | `/api/hospital/upload-logo/` | Upload or replace hospital institutional logo | `multipart/form-data` | `IsHospitalAdmin`, `IsSuperAdmin` |
| `DELETE` | `/api/hospital/delete-logo/` | Delete hospital logo | None | `IsHospitalAdmin`, `IsSuperAdmin` |
| `POST` | `/api/facilities/{id}/upload-image/` | Upload or replace hospital facility image | `multipart/form-data` | `IsHospitalAdmin`, `IsSuperAdmin` |
| `DELETE` | `/api/facilities/{id}/delete-image/` | Delete facility image | None | `IsHospitalAdmin`, `IsSuperAdmin` |
| `POST` | `/api/announcements/{id}/upload-image/` | Upload or replace announcement banner image | `multipart/form-data` | `IsHospitalAdmin`, `IsSuperAdmin` |
| `DELETE` | `/api/announcements/{id}/delete-image/` | Delete announcement image | None | `IsHospitalAdmin`, `IsSuperAdmin` |
| `POST` | `/api/departments/{id}/upload-image/` | Upload or replace department image | `multipart/form-data` | `IsHospitalAdmin`, `IsSuperAdmin` |
| `DELETE` | `/api/departments/{id}/delete-image/` | Delete department image | None | `IsHospitalAdmin`, `IsSuperAdmin` |

#### 1. Upload Request Payload
- Form field: `photo` or `file` or `image` or `logo`
- Multipart form-data containing binary image file.

#### 2. Media Upload Success Response (`200 OK`):
```json
{
  "message": "Photo uploaded successfully.",
  "photo_url": "https://res.cloudinary.com/hospital-platform/image/upload/v1728410000/hospital-platform/doctors/doc_abc123.jpg",
  "image_public_id": "hospital-platform/doctors/doc_abc123"
}
```

#### 3. Media Deletion Success Response (`200 OK`):
```json
{
  "message": "Photo deleted successfully."
}
```

#### 4. Validation & Error Responses (`400 Bad Request`):
```json
{
  "error": "File size exceeds 5MB limit (current: 6.2MB)."
}
```
```json
{
  "error": "Unsupported image format 'image/svg+xml'. Supported formats: image/jpeg, image/png, image/webp."
}
```
```json
{
  "error": "The uploaded file is not a valid or readable image."
}
```

#### 5. Safe Replacement Workflow:
1. Upload and validate new file.
2. Store new file on Cloudinary.
3. Update model record in PostgreSQL.
4. Safely destroy old asset on Cloudinary.
5. If upload or DB update fails, original image remains intact.

---

## 3. Strict Boundary Compliance & Completed Status

1. **Authentication & RBAC**: Fully implemented in Phase 12 via `/api/auth/` (JWT login, register, refresh, me, logout with blacklist) and DRF role permissions.
2. **Transactional Booking & Concurrency**: Fully implemented in Phase 13. Features authoritative backend availability, deterministic slot generation, PostgreSQL row-level locking via `select_for_update()`, atomic transactions, cancellation, rescheduling, double-booking prevention, and idempotency protection.
3. **Redis, Celery & Async Notifications**: Fully implemented in Phase 14. Real Redis message broker, Celery workers, Celery Beat periodic reminders, bounded retries with exponential backoff, transaction-safe dispatch, failure isolation, and PostgreSQL notification status tracking.
4. **Cloudinary / Media Upload Integration**: Fully implemented in Phase 15. Real Cloudinary media service, Pillow image validation, safe replacement workflow, safe deletion, RBAC permissions, and serializer URL resolution.
5. **Comprehensive Testing & Security Hardening**: Fully implemented in Phase 16. Includes Redis-backed throttling, exception sanitization, security headers, IDOR protection, PII/secret masking, and 35 security verification tests.
6. **Production Deployment & Reverse Proxy**: Fully implemented in Phase 17. Docker multi-stage images, Gunicorn WSGI server, Nginx reverse proxy with client IP forwarding, health probes, collectstatic, backup/restore procedures, and 7-service Docker Compose stack.
7. **Final Documentation & Quality Verification**: Fully implemented in Phase 18. Complete regression verification, repository hygiene, architecture documentation, and project handoff runbook.

---

## 4. System Health Endpoints

### 4.1 Gateway Health Probe (Nginx)
- **Route**: `GET /health`
- **Permissions**: `AllowAny`
- **Response**: `200 OK`
  ```json
  {
    "status": "ok",
    "service": "hospital-platform-nginx"
  }
  ```

### 4.2 Standard API Health Check
- **Route**: `GET /api/health/`
- **Permissions**: `AllowAny`
- **Response**: `200 OK`
  ```json
  {
    "status": "ok",
    "service": "hospital-platform-api"
  }
  ```

### 4.3 Detailed Infrastructure Health Probe
- **Route**: `GET /api/health/?detailed=1`
- **Permissions**: `AllowAny`
- **Verification**: Executes live query against PostgreSQL (`SELECT 1;`) and pings Redis cache.
- **Response**: `200 OK`
  ```json
  {
    "status": "ok",
    "service": "hospital-platform-api",
    "details": {
      "database": "connected",
      "redis": "connected"
    }
  }
  ```


