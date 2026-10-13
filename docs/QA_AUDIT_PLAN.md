# Eagle Sora Hospital Platform — Comprehensive QA Audit Plan

**Document Version:** 1.0  
**Audit Date:** October 2026  
**Project:** Eagle Sora Hospital Platform  
**Target Architecture:**
- **Frontend:** React 18, React Router v6, Vite, i18next (English, Hindi, Marathi), Vanilla CSS + Bootstrap Utility Baseline
- **Backend:** Django 5.x, Django REST Framework, SimpleJWT (RBAC), Celery 5.x
- **Database:** PostgreSQL 16 (docker named volume `postgres_data`)
- **Infrastructure:** Docker Compose, Nginx Reverse Proxy, Redis 7 (Cache & Celery Broker)

---

## 1. Inventory Baseline

### 1.1 Discovered Frontend Routes
| Route | Component | Access Gate | Description |
| :--- | :--- | :--- | :--- |
| `/` | `HomePage` | Public | Hero, quick appointment launcher, specialties, featured doctors, OPD visiting hours |
| `/about` | `AboutPage` | Public | Mission, institutional governance, clinical excellence, hospital accreditations |
| `/departments` | `DepartmentsPage` | Public | Clinical departments directory with consultant counts and OPD details |
| `/departments/:slug` | `DepartmentDetailPage` | Public | In-depth department profile, clinical consultants, treatments, FAQs |
| `/doctors` | `DoctorsPage` | Public | Complete medical staff roster with department, specialty, and OPD filters |
| `/doctors/:slug` | `DoctorDetailPage` | Public | Consultant physician bio, qualifications, OPD clinic schedule, fee, book button |
| `/doctors/:slug/availability` | `DoctorAvailabilityPage` | Public | Calendar matrix of doctor shifts, working days, and slot availability |
| `/appointments/book` | `BookAppointmentPage` | Public / Patient | 4-step consultation booking flow (Doctor, Date/Slot, Patient Info, Review) |
| `/appointments/result` | `AppointmentResultPage` | Public / Patient | Booking confirmation receipt with reference code and printable instructions |
| `/my-appointments` | `MyAppointmentsPage` | Patient Portal | Outpatient booking history, upcoming appointments, cancellation actions |
| `/my-appointments/:reference`| `AppointmentDetailPage` | Patient Portal | Single appointment consultation details, venue, cancel/reschedule |
| `/profile` | `PatientProfilePage` | Patient Portal | Patient demographics, emergency contact, MRN record |
| `/contact` | `ContactPage` | Public | Emergency hotline, hospital directions, contact inquiry form |
| `/staff/login` | `StaffLoginPage` | Staff / Admin | Unlinked staff gateway for SimpleJWT authentication |
| `/admin` | `AdminDashboardPage` | Staff / Admin | Operations overview, key clinical metrics, today's appointments summary |
| `/admin/doctors` | `AdminDoctorsPage` | Staff / Admin | Doctor CRUD, active status toggles, photo uploads, department assignment |
| `/admin/departments` | `AdminDepartmentsPage`| Staff / Admin | Department management, OPD operational rooms, heads of department |
| `/admin/schedules` | `AdminSchedulesPage` | Staff / Admin | Weekly OPD doctor schedules, shift timings, slot duration, breaks |
| `/admin/appointments` | `AdminAppointmentsPage`| Staff / Admin | Clinical appointment queue, status transitions (Checked-In, Completed, Cancelled) |
| `/admin/patients` | `AdminPatientsPage` | Staff / Admin | Patient outpatient directory, MRN indexing, contact verification |
| `/admin/content` | `AdminContentPage` | Staff / Admin | Hospital announcements, public notices, patient care FAQs |
| `/admin/notifications` | `AdminNotificationsPage`| Staff / Admin | Automated SMS/Email dispatch logs, Celery async task dispatch verification |
| `/admin/administrators` | `AdminAdministratorsPage`| Super Admin | Provisioning & deactivation of Hospital Administrators, RBAC assignments |
| `/admin/audit` | `AdminAuditPage` | Super Admin | Compliance and administrative security audit trail |
| `*` | `NotFoundPage` | Public | 404 fallback page with navigation recovery buttons |

---

### 1.2 Discovered API Endpoints & DB Mapping
| REST Endpoint | HTTP Methods | DRF View / ViewSet | Model | DB Table | Permissions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/auth/login/` | POST | `LoginView` | `User` | `accounts_user` | AllowAny (Throttled) |
| `/api/auth/register/` | POST | `RegisterView` | `User`, `PatientProfile` | `accounts_user`, `accounts_patientprofile` | AllowAny (Throttled) |
| `/api/auth/me/` | GET | `CurrentUserView` | `User` | `accounts_user` | IsAuthenticated |
| `/api/auth/logout/` | POST | `LogoutView` | `BlacklistedToken` | `token_blacklist_*` | IsAuthenticated |
| `/api/patients/` | GET, POST, PUT, PATCH | `PatientProfileViewSet` | `PatientProfile` | `accounts_patientprofile` | IsPatientOwnerOrStaff |
| `/api/administrators/`| GET, POST, PATCH | `AdministratorViewSet` | `User` | `accounts_user`, `auth_group` | IsSuperAdmin |
| `/api/administrators/:id/toggle-status/` | POST | `AdministratorViewSet` | `User` | `accounts_user` | IsSuperAdmin |
| `/api/hospital/profile/` | GET | `HospitalProfileView` | `HospitalProfile` | `hospital_hospitalprofile` | AllowAny |
| `/api/departments/` | GET, POST, PUT, PATCH | `DepartmentViewSet` | `Department` | `departments_department` | IsAdminUserOrReadOnly |
| `/api/doctors/` | GET, POST, PUT, PATCH | `DoctorViewSet` | `Doctor` | `doctors_doctor` | IsAdminUserOrReadOnly |
| `/api/doctors/:id/photo/` | POST | `DoctorPhotoUploadView` | `Doctor` | `doctors_doctor` | CanManageDoctorMedia |
| `/api/specialties/` | GET, POST | `SpecialtyViewSet` | `Specialty` | `doctors_specialty` | IsAdminUserOrReadOnly |
| `/api/schedules/` | GET, POST, PUT, PATCH | `DoctorScheduleViewSet` | `DoctorSchedule` | `scheduling_doctorschedule` | IsAdminUserOrReadOnly |
| `/api/schedules/availability/` | GET | `DoctorScheduleViewSet` | `DoctorSchedule` | `scheduling_doctorschedule` | AllowAny |
| `/api/schedules/leaves/`| GET, POST, DELETE | `DoctorLeaveViewSet` | `DoctorLeave` | `scheduling_doctorleave` | IsStaffOrAdmin |
| `/api/schedules/overrides/`| GET, POST, DELETE| `ScheduleOverrideViewSet` | `ScheduleOverride` | `scheduling_scheduleoverride` | IsStaffOrAdmin |
| `/api/appointments/` | GET, POST | `AppointmentViewSet` | `Appointment` | `appointments_appointment` | AllowAny (Create) / Staff (List) |
| `/api/appointments/:ref/` | GET, PATCH | `AppointmentViewSet` | `Appointment` | `appointments_appointment` | IsPatientOwnerOrStaff |
| `/api/appointments/:ref/cancel/` | POST | `AppointmentViewSet.cancel` | `Appointment` | `appointments_appointment` | IsPatientOwnerOrStaff |
| `/api/appointments/:ref/reschedule/` | POST | `AppointmentViewSet.reschedule`| `Appointment` | `appointments_appointment` | IsPatientOwnerOrStaff |
| `/api/appointments/:ref/pdf/` | GET | `AppointmentViewSet.download_pdf`| `Appointment` | `appointments_appointment` | IsPatientOwnerOrStaff |
| `/api/notifications/`| GET | `NotificationViewSet` | `Notification` | `notifications_notification` | IsStaffOrAdmin |
| `/api/audit/` | GET | `AuditLogViewSet` | `AuditLog` | `notifications_auditlog` | IsSuperAdmin |
| `/api/health/` | GET | `health_check` | N/A (Probes DB/Redis) | N/A | AllowAny |

---

## 2. Testing Methodology & Phases

1. **Phase 1: Inventory and Baseline Verification** (Completed)
2. **Phase 2: Comprehensive Interaction Testing** (Every route, modal, button, and state)
3. **Phase 3: Public Website Audit** (Doctor directory, departments, contact, internationalization)
4. **Phase 4: Complete Appointment Journey & OPD Schedule Audit** (Doctor selection, slot generation, appointment booking, concurrency, slot blocking, non-working days)
5. **Phase 5: Patient Portal Audit** (Authentication, MRN, personal appointments, cancellation, session security)
6. **Phase 6: Hospital Operations Dashboard Audit** (Admin doctor/schedule/appointment management, RBAC enforcement)
7. **Phase 7: Django Built-in Admin & Auth Boundaries**
8. **Phase 8: PostgreSQL Database & REST API Integrity**
9. **Phase 9: Redis, Celery Workers, Beat, and Asynchronous Notifications**
10. **Phase 10: Comprehensive Security & Penetration Review**
11. **Phase 11: Viewport Responsiveness & WCAG Accessibility Review**
12. **Phase 12: Automated Regression Suite Execution**
13. **Phase 13: Prioritized Defect Remediation & Verification**
14. **Phase 14: Final Audit Report Compilation**
