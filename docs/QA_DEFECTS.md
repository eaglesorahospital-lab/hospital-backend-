# Eagle Sora Hospital Platform — Comprehensive Defect Log & Remediation Report

**Document Version:** 1.0  
**Audit Date:** October 2026  
**Project:** Eagle Sora Hospital Platform  
**Target Environment:** Dockerized Production Stack (Nginx, Django, React, PostgreSQL 16, Redis, Celery)

---

## 1. Defect Classification & Severity Matrix

| Severity Level | Definition | Count | Resolved |
| :--- | :--- | :---: | :---: |
| **P1 - Critical / High** | Core user journey broken, data integrity failure, or lack of DB persistence for critical health transactions. | 3 | 3 (100%) |
| **P2 - Medium** | Administrative module or API route misalignment causing 404s, routing conflicts, or in-memory mutations. | 4 | 4 (100%) |
| **P3 - Low** | Minor cosmetic, non-blocking telemetry or async retry warning handled gracefully by the runtime. | 1 | 1 (100%) |
| **TOTAL** | | **8** | **8 (100%)** |

---

## 2. Detailed Defect Records

---

### DEF-001 (P1 - High): Patient Portal Disconnected from PostgreSQL Database
- **Component / Route:** Frontend (`/my-appointments`, `/my-appointments/:reference`), `usePatientSession.js`, `AppointmentDetailPage.jsx`
- **Impact:** Appointments booked via the outpatient booking engine were stored in `sessionStorage` and PostgreSQL, but the Patient Portal relied strictly on local storage. Refreshing the browser in a new tab or clearing browser storage lost access to consultation records. Furthermore, clicking "Cancel Appointment" did not communicate the cancellation to Django backend (`/api/appointments/<reference>/cancel/`), leaving the slot reserved in the database.
- **Root Cause:**
  `usePatientSession.js` initialized state solely from `sessionStorage.getItem('eglesora_latest_appointment')` and demo data without calling the backend REST API. `AppointmentDetailPage.jsx` immediately displayed "Appointment Not Found" if the reference was not present in the local memory session.
- **Remediation Applied:**
  1. Updated `frontend/src/services/appointmentService.js` with `getAppointments`, `getAppointment(reference)`, `cancelAppointment(reference, reason)`, and `rescheduleAppointment`.
  2. Updated `frontend/src/hooks/usePatientSession.js` to automatically fetch appointments from `/api/appointments/` when an authenticated session exists, merging server and local records.
  3. Updated `frontend/src/pages/patient/AppointmentDetailPage.jsx` to implement an asynchronous fallback fetch (`appointmentService.getAppointment(reference)`) when an appointment is accessed directly via URL, complete with loading spinners and error handling.
  4. Wired `cancelAppointment` to invoke `POST /api/appointments/<reference>/cancel/` with CSRF/Bearer token headers.
- **Verification & Evidence:**
  - Booked appointment `APT-2026-A041AE` via API/Frontend.
  - Hard-refreshed `/appointments/APT-2026-A041AE` without session storage. Record loaded directly from PostgreSQL with consultant details.
  - Cancelled consultation; status updated to `CANCELLED` in PostgreSQL table `appointments_appointment`.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-002 (P1 - High): Admin Appointment Registry Lacked Database Persistence
- **Component / Route:** Frontend (`/admin/appointments`), `AdminAppointmentsPage.jsx`
- **Impact:** Clinic administrators updating appointment statuses (e.g., "Checked In", "Completed", "Cancelled") in the Operations Dashboard only mutated local React component state. Status updates and clinical notes were never sent to the Django backend or stored in PostgreSQL. Upon browser reload, the consultation queue reverted to its default state.
- **Root Cause:**
  `handleApplyStatusChange`, `handleConfirmCancel`, and `handleConfirmReschedule` inside `AdminAppointmentsPage.jsx` only called `setAppointmentsList((prev) => prev.map(...))` and lacked API integration with `/api/appointments/`.
- **Remediation Applied:**
  1. Imported `appointmentService` into `AdminAppointmentsPage.jsx`.
  2. Added a `useEffect` hook to fetch live consultation queues from `/api/appointments/?page_size=100` on mount.
  3. Converted `handleApplyStatusChange` to asynchronously call `appointmentService.updateAppointmentStatus(apt.reference, newStatus, statusNote)`.
  4. Converted `handleConfirmCancel` to call `appointmentService.cancelAppointment(apt.reference, reason)`.
  5. Converted `handleConfirmReschedule` to call `appointmentService.rescheduleAppointment(apt.reference, payload)`.
  6. Provided resilient local fallback and user notification if the server is offline or authentication token expires.
- **Verification & Evidence:**
  - Transitioned appointment `APT-2026-A041AE` from `CONFIRMED` to `CHECKED_IN`.
  - Re-queried database via API: status returned `CHECKED_IN`.
  - Frontend built cleanly via `npm run build` and tested in browser.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-003 (P2 - Medium): Admin Patient Directory Isolated from Database
- **Component / Route:** Frontend (`/admin/patients`), `AdminPatientsPage.jsx`, `patientService.js`
- **Impact:** Clinic administrators searching or registering outpatients in `/admin/patients` were modifying static demo arrays. Newly registered patients were never stored in `accounts_patientprofile`, preventing them from booking consultations.
- **Root Cause:**
  `AdminPatientsPage.jsx` used hardcoded `INITIAL_DEMO_PATIENTS` and did not communicate with `/api/patients/`.
- **Remediation Applied:**
  1. Created `frontend/src/services/patientService.js` supporting `getPatients()`, `getPatient(id)`, and `createPatient(payload)`.
  2. Updated `AdminPatientsPage.jsx` to fetch registered patients from `/api/patients/` on component mount.
  3. Updated `handleAddPatient` to call `await patientService.createPatient(newPatientForm)`, persisting first name, last name, DOB, gender, mobile, email, address, and MRN to PostgreSQL.
- **Verification & Evidence:**
  - Executed patient creation test via automated suite and admin page.
  - Record confirmed in PostgreSQL table `accounts_patientprofile`.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-004 (P2 - Medium): Admin Department Roster Mutations Not Persisted
- **Component / Route:** Frontend (`/admin/departments`), `AdminDepartmentsPage.jsx`, `departmentService.js`
- **Impact:** Modifying department operational status (Active/Inactive), updating OPD hours, or adding new clinical departments in the operations dashboard only updated local memory.
- **Root Cause:**
  `departmentService.js` lacked write/mutation endpoints (`createDepartment` and `updateDepartment`). `AdminDepartmentsPage.jsx` handlers (`handleToggleStatus`, `handleSaveEdit`, `handleAddDepartment`) did not invoke REST endpoints.
- **Remediation Applied:**
  1. Added `createDepartment(payload)` and `updateDepartment(slugOrId, payload)` to `departmentService.js`.
  2. Updated `AdminDepartmentsPage.jsx` to load live departments from `/api/departments/` on mount.
  3. Updated `handleToggleStatus`, `handleSaveEdit`, and `handleAddDepartment` to asynchronously dispatch mutations to `/api/departments/<slug>/` via PATCH and POST.
- **Verification & Evidence:**
  - Successfully verified department retrieval and updates through Nginx reverse proxy.
  - Verified active toggle reflected in database.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-005 (P2 - Medium): Missing `/api/hospital/profile/` Endpoint Alias (HTTP 404)
- **Component / Route:** Backend (`backend/apps/hospital/views.py`), URL Routing
- **Impact:** Frontend modules and API consumers requesting `GET /api/hospital/profile/` received HTTP 404 Not Found.
- **Root Cause:**
  `HospitalProfileViewSet` in `backend/apps/hospital/views.py` only defined an `@action(detail=False, methods=['get'], url_path='current')`. While `/api/hospital/profile/current/` existed, standard REST clients expecting `/api/hospital/profile/` failed.
- **Remediation Applied:**
  Added the `@action(detail=False, methods=['get'], url_path='profile')` endpoint to `HospitalProfileViewSet`, returning the authoritative hospital institution profile.
- **Verification & Evidence:**
  - Automated test probe: `GET /api/hospital/profile/` returned HTTP 200 with institutional details (`name: "EgleSora Hospital"`, NABH accreditations, and contact details).
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-006 (P2 - Medium): Nginx Misrouting of SPA `/admin/*` Routes to Django Admin
- **Component / Route:** Infrastructure (`docker/nginx/nginx.conf`, `nginx/nginx.conf`)
- **Impact:** Refreshing or navigating directly to `/admin/administrators` in the React Operations Dashboard caused Nginx to redirect the user to Django built-in admin `/admin/login/`, breaking the Single Page Application experience.
- **Root Cause:**
  Nginx regex `location ^~ /admin/` matched all URL prefixes starting with `/admin/` and proxied them to Django backend on port 8000 instead of allowing React Router to handle `/admin/administrators`.
- **Remediation Applied:**
  Restricted the backend Django admin proxy in Nginx configuration to specific Django administrative sub-paths (`/admin/login/`, `/admin/logout/`, `/admin/auth/`, `/admin/hospital/`, etc.) or query patterns, while serving `index.html` for React SPA dashboard routes.
- **Verification & Evidence:**
  - Navigated directly to `http://localhost/admin/administrators` and `http://localhost/admin/schedules`.
  - React SPA loaded without redirection to Django admin login.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-007 (P3 - Observation): Async SMTP Connection Refusal on Port 1025
- **Component / Route:** Celery Worker (`hospital_celery_worker`), Notification Dispatch
- **Impact:** Worker logs reported `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 1025)` when attempting to dispatch consultation confirmation emails.
- **Root Cause:**
  Local development Docker environment does not run an active MailHog / SMTP server on port 1025 by default.
- **Remediation & Resilience Assessment:**
  The notification service (`safe_dispatch_confirmation`) in `backend/apps/notifications/services.py` catches email connection exceptions and schedules Celery retries (up to 3 times) without terminating the Celery worker and without rolling back the database appointment booking transaction.
- **Verification & Evidence:**
  - Appointment booking completed with HTTP 201 Created and reference code generated in under 350ms.
  - Celery worker logged retry attempts and safely moved on to the next task in the Redis queue.
- **Status:** **RESILIENT BY DESIGN / VERIFIED**

---

### DEF-008 (P1 - High): "Check OPD Schedule" Flow Broken by Mock Data Coupling and Backend 500 Error
- **Component / Route:** Frontend (`/doctors/:slug/availability`), `DoctorAvailabilityPage.jsx`, `backend/apps/scheduling/views.py`
- **Impact:** Clicking "Check OPD Schedule" on doctor cards failed to show real consultation slots. All dates displayed "No Outpatient Clinic on [Day]s" because the page attempted to load slots using mock functions (`generateMockSlotsForDate`) keyed to old demo IDs (101-108) rather than PostgreSQL IDs (191-198). Furthermore, when any client queried `/api/schedules/availability/?doctor=<slug>`, Django threw an unhandled 500 Internal Server Error (`Field 'id' expected a number but got '<slug>'`).
- **Root Cause:**
  1. `backend/apps/scheduling/views.py` unconditionally filtered `Doctor.objects.filter(id=doctor_id)` without checking if `doctor_id` was a slug or integer, throwing a 500 on string slugs.
  2. `DoctorAvailabilityPage.jsx` did not call `scheduleService.getAvailabilityRange` or `scheduleService.getAvailability`. Instead, it called `generateMockSlotsForDate(doctor.id, ...)` which returned an empty array for database doctors, preventing patients from seeing real slots or proceeding to booking.
- **Remediation Applied:**
  1. Updated `DoctorScheduleViewSet.availability` in `backend/apps/scheduling/views.py` to inspect `doctor_id` format: if numeric, filter by `id`; if string, filter by `slug`.
  2. Overhauled `DoctorAvailabilityPage.jsx` to eliminate all mock scheduling imports and connect directly to `scheduleService.getAvailabilityRange` (for 7-day strip) and `scheduleService.getAvailability` (for live day slots from PostgreSQL).
  3. Added live slot selection, 12h time formatting, distinct closed/leave/available states, and a preselected slot booking link (`/appointments/book?doctor=<slug>&date=<date>&time=<time>`).
  4. Updated `useAppointmentBooking.js` to accept and synchronize preselected `time` URL parameters.
- **Verification & Evidence:**
  - Tested destination URLs `http://localhost/doctors/dr-rajesh-k-varma/availability` and `http://localhost/doctors/dr-priya-nair/availability` on both Nginx and Vite.
  - Verified working day returns 8 live slots (available/booked).
  - Verified closed day returns 0 slots with authoritative reason ("Sunday is a non-working day for this doctor.").
  - Successfully booked consultation from schedule slot and verified slot is locked in database.
- **Status:** **VERIFIED & RESOLVED**

---

### DEF-009 (P1 - High): Doctor Profile "View Weekly Time Slots" and Schedule Integration
- **Component / Route:** Frontend Doctor Detail Page (`/doctors/:slug`), `DoctorDetailPage.jsx`, `DoctorAvailabilityPage.jsx`
- **Impact:** 
  1. Clicking "View Weekly Time Slots" or "Check OPD Schedule" on `DoctorDetailPage.jsx` relied strictly on `doctor.slug`, which failed if a specialist was opened by database ID (e.g. `/doctors/191`), leading to invalid or broken navigation.
  2. The "Outpatient Working Schedule" table on `DoctorDetailPage.jsx` was hardcoded or defaulted to unpopulated mock properties; `doctor.schedule.breaks.map(b => `${b.start} - ${b.end}`)` evaluated to `undefined - undefined` because database records did not pass `schedule` within `DoctorDetailSerializer`.
  3. `DoctorDetailPage.jsx` did not fetch PostgreSQL `DoctorSchedule` or `DoctorLeave` records, displaying static/empty consultation hours and leaves.
- **Root Cause:**
  - `DoctorDetailPage.jsx` lacked integration with `scheduleService.getDoctorSchedules` and `scheduleService.getDoctorLeaves`.
  - Links to availability did not use a robust fallback identifier (`doctor.slug || doctor.id || identifier`).
  - Daily clinical breaks and consultation hours lacked defensive formatting for real database models.
- **Remediation Applied:**
  1. Integrated `DoctorDetailPage.jsx` with `scheduleService.getDoctorSchedules(identifier)` and `scheduleService.getDoctorLeaves(identifier)` alongside `doctorService.getDoctor(identifier)` via `Promise.allSettled`.
  2. Implemented `doctorIdentifier = doctor.slug || doctor.id || identifier;` ensuring reliable navigation for both numeric IDs and slug routes across "View Weekly Time Slots", "Check OPD Schedule", and "Book Consultation".
  3. Formatted working hours and midday breaks using live `DoctorSchedule` records and 12-hour time format (`formatTime12h`).
  4. Formatted upcoming leave notices using live `DoctorLeave` records from PostgreSQL.
  5. Added server error notification with retry button on API failure.
  6. Verified end-to-end regression across both production Nginx (`http://localhost`) and Vite development server (`http://localhost:3002`).
- **Verification & Evidence:**
  - Verified navigation from Doctor Directory -> Doctor Card "Check OPD Schedule".
  - Verified navigation from Doctor Profile -> "View Weekly Time Slots" on Dr. Rajesh K. Varma and Dr. Priya Nair.
  - Verified live slot selection, preselected booking transition, step advancement (Step 2 -> Step 3 -> Step 4), page reload preservation, and invalid doctor ID handling.
- **Status:** **VERIFIED & RESOLVED**
