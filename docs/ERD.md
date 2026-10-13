# Entity Relationship Diagram (ERD) & Backend Domain Models

## Provenance: Phase 0 Foundation (Initial) → Phase 10 Backend Domain Models Specification

This document provides the complete PostgreSQL domain model schema specification, relationship diagrams, constraints, choices/enums, and deletion behaviors for the Eagle Sora Hospital Platform. Initialized in Phase 0 Foundation.

---

## 1. Visual Entity Relationship Diagram (Mermaid)

```mermaid
erDiagram
    User ||--o| PatientProfile : "has profile (OneToOne, CASCADE)"
    User ||--o| Doctor : "has profile (OneToOne, SET_NULL)"
    User ||--o{ AuditLog : "acts in (ForeignKey, SET_NULL)"
    User ||--o{ Notification : "receives (ForeignKey, CASCADE)"

    Department ||--o{ Doctor : "employs (ForeignKey, PROTECT)"
    Department ||--o{ DepartmentService : "offers (ForeignKey, CASCADE)"
    Department ||--o{ DepartmentFAQ : "answers (ForeignKey, CASCADE)"
    Department ||--o{ Appointment : "categorizes (ForeignKey, PROTECT)"

    Specialty ||--o{ Doctor : "specializes in (ForeignKey, PROTECT)"

    Doctor ||--o{ DoctorSchedule : "configures (ForeignKey, CASCADE)"
    Doctor ||--o{ DoctorLeave : "requests (ForeignKey, CASCADE)"
    Doctor ||--o{ ScheduleOverride : "overrides (ForeignKey, CASCADE)"
    Doctor ||--o{ Appointment : "conducts (ForeignKey, PROTECT)"

    DoctorSchedule ||--o{ ScheduleBreak : "includes (ForeignKey, CASCADE)"

    PatientProfile ||--o{ Appointment : "books (ForeignKey, PROTECT)"

    Appointment ||--o{ Notification : "triggers (ForeignKey, CASCADE)"

    HospitalProfile ||--o{ HospitalFacility : "features (optional/global)"
    HospitalProfile ||--o{ HospitalAnnouncement : "publishes (optional/global)"
    HospitalProfile ||--o{ HospitalFAQ : "answers (optional/global)"

    User {
        bigint id PK
        string email UK
        string username UK
        string first_name
        string last_name
        string phone
        string role
        boolean is_active
        boolean is_staff
        boolean is_superuser
        timestamp date_joined
        timestamp updated_at
    }

    PatientProfile {
        bigint id PK
        bigint user_id FK,UK
        string mrn UK
        date date_of_birth
        string gender
        string blood_group
        string phone
        string emergency_contact
        text address
        timestamp created_at
        timestamp updated_at
    }

    HospitalProfile {
        bigint id PK
        string name
        text tagline
        text overview
        string email
        string phone
        string emergency_phone
        text address
        string visiting_hours
        text emergency_info
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    HospitalFacility {
        bigint id PK
        string name
        text description
        string icon_name
        int display_order
        boolean is_active
        timestamp created_at
    }

    HospitalAnnouncement {
        bigint id PK
        string title
        string slug UK
        text content
        boolean is_published
        timestamp published_at
        timestamp created_at
        timestamp updated_at
    }

    HospitalFAQ {
        bigint id PK
        text question
        text answer
        int display_order
        boolean is_active
        timestamp created_at
    }

    Department {
        bigint id PK
        string name UK
        string slug UK
        text description
        string contact_email
        string contact_phone
        string location
        string operating_hours
        string image
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    DepartmentService {
        bigint id PK
        bigint department_id FK
        string name
        text description
        int display_order
        boolean is_active
        timestamp created_at
    }

    DepartmentFAQ {
        bigint id PK
        bigint department_id FK
        text question
        text answer
        int display_order
        boolean is_active
        timestamp created_at
    }

    Specialty {
        bigint id PK
        string name UK
        string slug UK
        text description
        boolean is_active
        timestamp created_at
    }

    Doctor {
        bigint id PK
        bigint user_id FK,UK
        bigint department_id FK
        bigint specialty_id FK
        string name
        string slug UK
        string qualification
        int experience_years
        text bio
        text expertise
        string consultation_type
        int consultation_duration_minutes
        string room_location
        string image
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    DoctorSchedule {
        bigint id PK
        bigint doctor_id FK
        int day_of_week
        time start_time
        time end_time
        boolean is_working
        int slot_duration_minutes
        int capacity
        string timezone
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    ScheduleBreak {
        bigint id PK
        bigint schedule_id FK
        time start_time
        time end_time
        string label
        timestamp created_at
    }

    DoctorLeave {
        bigint id PK
        bigint doctor_id FK
        date start_date
        date end_date
        string reason
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    ScheduleOverride {
        bigint id PK
        bigint doctor_id FK
        date override_date
        time start_time
        time end_time
        string availability_state
        int slot_duration_minutes
        int capacity
        string reason
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    Appointment {
        bigint id PK
        string reference UK
        bigint patient_id FK
        bigint doctor_id FK
        bigint department_id FK
        date appointment_date
        time start_time
        time end_time
        string appointment_type
        string status
        text reason_for_visit
        text notes
        text cancellation_reason
        timestamp cancelled_at
        string rescheduled_to_reference
        timestamp created_at
        timestamp updated_at
    }

    Notification {
        bigint id PK
        bigint recipient_id FK
        bigint appointment_id FK
        string notification_type
        string channel
        string status
        string subject
        text message
        string provider_reference
        timestamp sent_at
        timestamp failed_at
        timestamp created_at
        timestamp updated_at
    }

    AuditLog {
        bigint id PK
        bigint actor_id FK
        string role
        string action
        string resource_type
        string resource_id
        string result
        jsonb metadata
        string ip_address
        timestamp timestamp
    }
```

---

## 2. Domain Models & Architecture Breakdown

### 2.1 Accounts Domain (`backend/apps/accounts`)
- **`User`**: Custom user inheriting from `AbstractUser`. Uses `email` as `USERNAME_FIELD` (case-insensitive uniqueness via custom UserManager).
  - **Roles**:
    - `SUPER_ADMIN` — System superuser with complete access.
    - `HOSPITAL_ADMIN` — Hospital administration staff managing doctors, schedules, announcements, and metrics.
    - `DOCTOR_STAFF` — Medical staff managing appointments, overrides, and leaves.
    - `PATIENT` — Public registered patient booking and reviewing appointments.
- **`PatientProfile`**: Linked via `OneToOneField(User, on_delete=CASCADE)`. Contains medical record number (`mrn`), gender, blood group, emergency contact details, and residential address. Does not store sensitive clinical notes.

### 2.2 Hospital Domain (`backend/apps/hospital`)
- **`HospitalProfile`**: Singleton-style institutional overview holding facility name, overview, emergency contacts, visiting hours, and address.
- **`HospitalFacility`**: Hospital amenities and infrastructure items (e.g. ICU, 24/7 Pharmacy, Diagnostic Lab).
- **`HospitalAnnouncement`**: Public announcements with slugs and publication dates.
- **`HospitalFAQ`**: Institutional frequently asked questions.

### 2.3 Departments Domain (`backend/apps/departments`)
- **`Department`**: Medical specialties/divisions (e.g. Cardiology, Neurology) with unique slugs, operating hours, and contact details.
- **`DepartmentService`**: Specific clinical procedures or services offered by the department.
- **`DepartmentFAQ`**: Department-specific frequently asked questions.

### 2.4 Doctors Domain (`backend/apps/doctors`)
- **`Specialty`**: Distinct medical specialty classifications (e.g. Interventional Cardiology).
- **`Doctor`**: Medical practitioner profile. Linked optionally to `User` (`OneToOneField, on_delete=SET_NULL`), `Department` (`ForeignKey, on_delete=PROTECT`), and `Specialty` (`ForeignKey, on_delete=PROTECT`).
  - Supports bio, qualifications, experience years, consultation duration (minutes), consultation type (`IN_PERSON`, `VIDEO`, `BOTH`), and profile image.

### 2.5 Scheduling Domain (`backend/apps/scheduling`)
- **`DoctorSchedule`**: Weekly recurring availability template for each doctor (days 0–6, Monday–Sunday). Defines `start_time`, `end_time`, `slot_duration_minutes`, `capacity`, and IANA `timezone`.
- **`ScheduleBreak`**: Daily break intervals within a schedule (e.g. Lunch 13:00–14:00).
- **`DoctorLeave`**: Multi-day or single-day leaves requested by the doctor.
- **`ScheduleOverride`**: Date-specific schedule exceptions overriding the weekly pattern (e.g. custom shifts, emergency unavailability).

### 2.6 Appointments Domain (`backend/apps/appointments`)
- **`Appointment`**: Core booking entity connecting `PatientProfile`, `Doctor`, and `Department`.
  - **Reference**: High-entropy human-readable identifier (`APT-YYYY-XXXXXX`), unique and indexed.
  - **Lifecycle States** (matching PDF specifications):
    - `REQUESTED` — Awaiting administrative/clinic confirmation.
    - `CONFIRMED` — Confirmed and scheduled.
    - `CHECKED_IN` — Patient has arrived at the clinic/hospital.
    - `COMPLETED` — Consultation concluded.
    - `CANCELLED` — Consultation cancelled (retains `cancellation_reason` and `cancelled_at`).
    - `NO_SHOW` — Patient failed to attend.
    - `RESCHEDULED` — Replaced by a new appointment reference.

### 2.7 Notifications & Audit Domain (`backend/apps/notifications`)
- **`Notification`**: Audit of outgoing communications across channels.
  - **Types**: `APPOINTMENT_CONFIRMATION`, `APPOINTMENT_REMINDER`, `APPOINTMENT_CANCELLATION`, `APPOINTMENT_RESCHEDULE`, `ADMIN_ALERT`.
  - **Channels**: `EMAIL`, `SMS`, `SYSTEM`.
  - **Statuses**: `PENDING`, `SENT`, `FAILED`.
- **`AuditLog`**: Immutable activity trail recording user actions, resource references, results, and JSON metadata.

---

## 3. Database Constraints & Validations

| Model | Constraint / Rule | Type | Description |
|---|---|---|---|
| `User` | `email` unique | `UniqueConstraint` | Ensures email addresses are globally unique across all accounts. |
| `PatientProfile` | `mrn` unique | `UniqueConstraint` | Unique Medical Record Number per patient. |
| `Department` | `name` & `slug` unique | `UniqueConstraint` | Prevents naming or routing collisions. |
| `Specialty` | `name` & `slug` unique | `UniqueConstraint` | Prevents naming or routing collisions. |
| `Doctor` | `slug` unique | `UniqueConstraint` | URL slug uniqueness for public doctor profile routing. |
| `DoctorSchedule` | `(doctor, day_of_week)` unique | `UniqueConstraint` | Exactly one weekly schedule rule per doctor per day. |
| `DoctorSchedule` | `start_time < end_time` | `CheckConstraint` + `clean()` | Ensures valid non-inverted time windows. |
| `DoctorSchedule` | `slot_duration_minutes > 0` | `CheckConstraint` | Positive slot duration. |
| `DoctorSchedule` | `capacity > 0` | `CheckConstraint` | Positive patient capacity per slot. |
| `ScheduleBreak` | `start_time < end_time` | `CheckConstraint` + `clean()` | Ensures valid break time windows. |
| `DoctorLeave` | `start_date <= end_date` | `CheckConstraint` + `clean()` | Ensures end date never precedes start date. |
| `ScheduleOverride` | `start_time < end_time` | `CheckConstraint` + `clean()` | Valid override operational hours. |
| `Appointment` | `reference` unique | `UniqueConstraint` | Safe, unforgeable external appointment reference. |
| `Appointment` | `start_time < end_time` | `CheckConstraint` + `clean()` | Valid consultation duration window. |

---

## 4. Deletion Strategy & Data Integrity

Critical clinical and scheduling records are protected against cascade deletion:

- **`Appointment -> Doctor`**: `on_delete=models.PROTECT`. Doctors with historical appointments cannot be hard-deleted; their records are retained and deactivated via `is_active=False`.
- **`Appointment -> Department`**: `on_delete=models.PROTECT`. Departments with appointments cannot be casually removed.
- **`Appointment -> PatientProfile`**: `on_delete=models.PROTECT`. Historical appointments remain attached to patient records for clinical continuity.
- **`Doctor -> User`**: `on_delete=models.SET_NULL`. Deleting a staff user account does not destroy doctor historical records or associations.
- **`AuditLog -> User`**: `on_delete=models.SET_NULL`. Deleting a user account retains historical audit trail logs with `actor=NULL`.
- **`Notification -> User` / `Appointment`**: `on_delete=models.CASCADE`. Notifications are transient operational records cleanly purged if the parent entity is purged.
- **Sub-entities** (`DoctorSchedule`, `ScheduleBreak`, `DoctorLeave`, `DepartmentService`, `DepartmentFAQ`): `on_delete=models.CASCADE` when parent doctor or department is intentionally decommissioned.

---

## 5. Indexing Strategy

To guarantee sub-second read performance for appointment lookups, doctor listings, and administrative dashboards, indexes are created on:

- **Appointments**: `reference` (unique index), `(doctor, appointment_date, status)`, `(patient, appointment_date)`, `appointment_date`, `status`.
- **Doctors**: `slug` (unique index), `(department, is_active)`, `(specialty, is_active)`.
- **Schedules**: `(doctor, day_of_week, is_active)`.
- **Overrides**: `(doctor, override_date)`.
- **Leaves**: `(doctor, start_date, end_date)`.
- **Notifications**: `(recipient, status)`, `(appointment, notification_type)`, `status`, `created_at`.
- **Audit Logs**: `(actor, timestamp)`, `(resource_type, resource_id)`, `timestamp`.
