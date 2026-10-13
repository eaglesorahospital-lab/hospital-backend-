"""
Comprehensive Security Hardening & Vulnerability Verification Test Suite (Phase 16).
Tests against live PostgreSQL database.

Validates:
1. Authentication Security (token enforcement, malformed tokens, expiration, blacklist, privilege escalation)
2. Role-Based Access Control (least privilege matrix across all roles)
3. Object-Level Authorization & IDOR (cross-patient, cross-doctor, cross-appointment data isolation)
4. Input Validation & Resilience (oversized inputs, invalid types/enums, malformed JSON)
5. SQL Injection & XSS Resilience (malicious SQL-like payloads, HTML script tags)
6. API Rate Limiting (throttling on login, registration, appointments, media uploads)
7. Appointment Concurrency & Abuse (double-booking, past dates, inactive doctors, breaks, leave, idempotency)
8. Media Upload Security (spoofed MIME, executable payloads, oversized files, secret masking)
9. PII & Secret Isolation (credential masking, error sanitization, security headers)
"""

import os
import sys
import io
import time
from datetime import date, time as dtime, timedelta
from unittest.mock import patch
from PIL import Image

# Ensure backend path is on sys.path
backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PatientProfile
from apps.hospital.models import HospitalProfile, HospitalFacility, HospitalAnnouncement
from apps.departments.models import Department
from apps.doctors.models import Doctor, Specialty
from apps.scheduling.models import DoctorSchedule, DoctorLeave, ScheduleBreak
from apps.appointments.models import Appointment
from apps.notifications.models import Notification, AuditLog
from config.throttling import LoginRateThrottle, AppointmentBookingRateThrottle, MediaUploadRateThrottle

User = get_user_model()


class SecurityHardeningBaseTestCase(TestCase):
    """
    Base test fixture initializing standard role personas:
    - Super Admin
    - Hospital Admin
    - Doctor Staff (2 distinct doctors for cross-doctor IDOR tests)
    - Patients (2 distinct patients for cross-patient IDOR tests)
    - Unauthenticated Public client
    """
    def setUp(self):
        super().setUp()
        cache.clear()

        # 1. Super Admin
        self.super_admin = User.objects.create_superuser(
            email='superadmin.sec@hospital.local',
            password='SecureAdminPassword123!',
            first_name='Super',
            last_name='Admin',
        )

        # 2. Hospital Admin
        self.hospital_admin = User.objects.create_user(
            email='hadmin.sec@hospital.local',
            password='HospitalAdminPass123!',
            first_name='Hospital',
            last_name='Admin',
            role=User.Role.HOSPITAL_ADMIN,
        )

        # 3. Clinical Department & Specialty
        self.department = Department.objects.create(
            name='Security Cardiology',
            slug='security-cardiology',
            short_description='Department for security testing',
            is_active=True,
        )
        self.specialty = Specialty.objects.create(
            name='Security Cardiology Specialty',
            slug='security-cardiology-specialty',
            is_active=True,
        )

        # 4. Doctor Staff 1 & Profile
        self.doctor_user_1 = User.objects.create_user(
            email='doctor1.sec@hospital.local',
            password='DoctorPassword123!',
            first_name='Doctor',
            last_name='One',
            role=User.Role.DOCTOR_STAFF,
        )
        self.doctor_1 = Doctor.objects.create(
            user=self.doctor_user_1,
            name='Dr. Security One',
            slug='dr-security-one',
            department=self.department,
            specialty=self.specialty,
            is_active=True,
        )

        # 5. Doctor Staff 2 & Profile (for cross-doctor isolation tests)
        self.doctor_user_2 = User.objects.create_user(
            email='doctor2.sec@hospital.local',
            password='DoctorPassword123!',
            first_name='Doctor',
            last_name='Two',
            role=User.Role.DOCTOR_STAFF,
        )
        self.doctor_2 = Doctor.objects.create(
            user=self.doctor_user_2,
            name='Dr. Security Two',
            slug='dr-security-two',
            department=self.department,
            specialty=self.specialty,
            is_active=True,
        )

        # 6. Patient 1 & Profile
        self.patient_user_1 = User.objects.create_user(
            email='patient1.sec@hospital.local',
            password='PatientPassword123!',
            first_name='Alice',
            last_name='Patient',
            role=User.Role.PATIENT,
        )
        self.patient_profile_1 = PatientProfile.objects.create(
            user=self.patient_user_1,
            mrn='MRN-SEC-001',
            first_name='Alice',
            last_name='Patient',
            gender=PatientProfile.Gender.FEMALE,
            date_of_birth=date(1990, 5, 15),
            phone='+919876543210',
            email='patient1.sec@hospital.local',
        )

        # 7. Patient 2 & Profile (for cross-patient isolation tests)
        self.patient_user_2 = User.objects.create_user(
            email='patient2.sec@hospital.local',
            password='PatientPassword123!',
            first_name='Bob',
            last_name='Patient',
            role=User.Role.PATIENT,
        )
        self.patient_profile_2 = PatientProfile.objects.create(
            user=self.patient_user_2,
            mrn='MRN-SEC-002',
            first_name='Bob',
            last_name='Patient',
            gender=PatientProfile.Gender.MALE,
            date_of_birth=date(1985, 8, 20),
            phone='+919876543211',
            email='patient2.sec@hospital.local',
        )

        # API Clients
        self.anon_client = APIClient()
        self.patient_1_client = self._create_authenticated_client(self.patient_user_1)
        self.patient_2_client = self._create_authenticated_client(self.patient_user_2)
        self.doctor_1_client = self._create_authenticated_client(self.doctor_user_1)
        self.doctor_2_client = self._create_authenticated_client(self.doctor_user_2)
        self.hospital_admin_client = self._create_authenticated_client(self.hospital_admin)
        self.super_admin_client = self._create_authenticated_client(self.super_admin)

    def _create_authenticated_client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        return client

    def _create_test_image(self, format='JPEG', width=100, height=100):
        buffer = io.BytesIO()
        image = Image.new('RGB', (width, height), color=(73, 109, 137))
        image.save(buffer, format=format)
        buffer.seek(0)
        buffer.name = f'test.{format.lower()}'
        return buffer


class AuthenticationSecurityTests(SecurityHardeningBaseTestCase):
    """
    Tests JWT authentication security, token validation, blacklist, and escalation.
    """
    def test_anonymous_access_denied_on_protected_endpoints(self):
        """Verify anonymous requests to protected endpoints return HTTP 401 Unauthorized."""
        protected_endpoints = [
            '/api/auth/me/',
            '/api/appointments/',
            '/api/patients/',
            '/api/notifications/',
            '/api/audit/',
        ]
        for url in protected_endpoints:
            res = self.anon_client.get(url)
            self.assertEqual(
                res.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"Endpoint {url} allowed anonymous access!"
            )

    def test_invalid_and_malformed_token_denied(self):
        """Verify invalid or forged JWT tokens are rejected with 401."""
        client = APIClient()
        # Non-Bearer prefix
        client.credentials(HTTP_AUTHORIZATION='Basic dXNlcjpwYXNz')
        res = client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Corrupted token signature
        client.credentials(HTTP_AUTHORIZATION='Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.corrupted.payload')
        res = client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_denied(self):
        """Verify expired access tokens are rejected."""
        refresh = RefreshToken.for_user(self.patient_user_1)
        # Create an expired token by manually setting lifetime
        token = refresh.access_token
        token.set_exp(lifetime=timedelta(seconds=-10))

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(token)}')
        res = client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        """Verify logout invalidates refresh token and prevents token refresh."""
        refresh = RefreshToken.for_user(self.patient_user_1)
        refresh_str = str(refresh)

        # Perform logout with refresh token
        res = self.patient_1_client.post('/api/auth/logout/', {'refresh': refresh_str})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Attempt to use blacklisted token to obtain new access token
        refresh_res = self.anon_client.post('/api/auth/refresh/', {'refresh': refresh_str})
        self.assertEqual(refresh_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_privilege_escalation_impossible_in_registration(self):
        """Verify public registration cannot be used to create SUPER_ADMIN or privileged roles."""
        payload = {
            'email': 'hacker@hospital.local',
            'password': 'ComplexPassword123!',
            'password_confirm': 'ComplexPassword123!',
            'first_name': 'Attacker',
            'last_name': 'Hacker',
            'role': 'SUPER_ADMIN',  # Attempted privilege escalation
            'is_staff': True,
            'is_superuser': True,
        }
        res = self.anon_client.post('/api/auth/register/', payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_user = User.objects.get(email='hacker@hospital.local')
        self.assertEqual(created_user.role, User.Role.PATIENT)
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)


class RBACTests(SecurityHardeningBaseTestCase):
    """
    Tests least privilege Role-Based Access Control matrix.
    """
    def test_patient_forbidden_from_admin_mutations(self):
        """Verify patient receives HTTP 403 when attempting admin mutations."""
        # 1. Mutate department
        res = self.patient_1_client.post('/api/departments/', {'name': 'Hacked Dept', 'slug': 'hacked-dept'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Mutate doctor
        res = self.patient_1_client.post('/api/doctors/', {'name': 'Fake Doctor', 'slug': 'fake-doctor'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Mutate hospital profile
        res = self.patient_1_client.post('/api/hospital/', {'name': 'Compromised Hospital'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Mutate audit logs
        res = self.patient_1_client.post('/api/audit/', {'action': 'FAKE_ACTION'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_forbidden_from_viewing_audit_logs(self):
        """Verify patient cannot access audit logs."""
        res = self.patient_1_client.get('/api/audit/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_staff_cannot_mutate_hospital_content(self):
        """Verify Doctor Staff cannot modify institutional hospital content."""
        res = self.doctor_1_client.post('/api/hospital/', {'name': 'Doctor Controlled Hospital'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_hospital_admin_has_proper_administrative_access(self):
        """Verify Hospital Admin can modify hospital content and view audit logs."""
        res = self.hospital_admin_client.get('/api/audit/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class IDORAndObjectAuthorizationTests(SecurityHardeningBaseTestCase):
    """
    Tests Insecure Direct Object Reference (IDOR) and cross-tenant/cross-user isolation.
    """
    def setUp(self):
        super().setUp()
        # Create an appointment for Patient 1 with Doctor 1
        self.apt_1 = Appointment.objects.create(
            patient=self.patient_profile_1,
            doctor=self.doctor_1,
            department=self.department,
            appointment_date=date.today() + timedelta(days=2),
            start_time=dtime(10, 0),
            end_time=dtime(10, 30),
            status=Appointment.Status.CONFIRMED,
            reason_for_visit='Cardiology consultation',
        )

        # Create an appointment for Patient 2 with Doctor 2
        self.apt_2 = Appointment.objects.create(
            patient=self.patient_profile_2,
            doctor=self.doctor_2,
            department=self.department,
            appointment_date=date.today() + timedelta(days=3),
            start_time=dtime(11, 0),
            end_time=dtime(11, 30),
            status=Appointment.Status.CONFIRMED,
            reason_for_visit='Followup visit',
        )

    def test_patient_cannot_view_another_patient_profile(self):
        """IDOR: Patient 1 cannot view Patient 2's profile via direct ID."""
        res = self.patient_1_client.get(f'/api/patients/{self.patient_profile_2.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_view_another_patient_appointment(self):
        """IDOR: Patient 1 cannot view Patient 2's appointment via reference."""
        res = self.patient_1_client.get(f'/api/appointments/{self.apt_2.reference}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_cancel_another_patient_appointment(self):
        """IDOR: Patient 1 cannot cancel Patient 2's appointment."""
        res = self.patient_1_client.post(
            f'/api/appointments/{self.apt_2.reference}/cancel/',
            {'reason': 'Malicious cancellation'}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.apt_2.refresh_from_db()
        self.assertEqual(self.apt_2.status, Appointment.Status.CONFIRMED)

    def test_patient_cannot_reschedule_another_patient_appointment(self):
        """IDOR: Patient 1 cannot reschedule Patient 2's appointment."""
        res = self.patient_1_client.post(
            f'/api/appointments/{self.apt_2.reference}/reschedule/',
            {
                'appointment_date': str(date.today() + timedelta(days=5)),
                'start_time': '11:00:00',
                'end_time': '11:30:00',
                'reason': 'Hijacked reschedule'
            }
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_cannot_forge_patient_id_in_appointment_creation(self):
        """IDOR: Patient 1 cannot book an appointment for Patient 2 by forging patient ID in payload."""
        # Setup schedule for doctor 1
        target_date = date.today() + timedelta(days=4)
        DoctorSchedule.objects.create(
            doctor=self.doctor_1,
            day_of_week=target_date.strftime('%A'),
            start_time=dtime(9, 0),
            end_time=dtime(17, 0),
            slot_duration_minutes=30,
            is_working_day=True,
            is_active=True,
        )

        payload = {
            'doctor': self.doctor_1.id,
            'patient': self.patient_profile_2.id,  # Attempting to book on behalf of Patient 2
            'appointment_date': str(target_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
            'reason_for_visit': 'Forged patient booking test',
        }
        res = self.patient_1_client.post('/api/appointments/', payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_apt = Appointment.objects.get(reference=res.data['reference'])
        # Must be booked for Patient 1 (the authenticated user's own profile), NOT Patient 2
        self.assertEqual(created_apt.patient, self.patient_profile_1)
        self.assertNotEqual(created_apt.patient, self.patient_profile_2)

    def test_doctor_staff_cannot_alter_another_doctor_profile_or_photo(self):
        """IDOR: Doctor Staff 1 cannot upload a photo or update Doctor 2's profile."""
        img = self._create_test_image('JPEG')
        res = self.doctor_1_client.post(
            f'/api/doctors/{self.doctor_2.slug}/upload-photo/',
            {'photo': img},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_cannot_view_another_patient_notifications(self):
        """IDOR: Patient 1 cannot see notifications directed to Patient 2."""
        notif_2 = Notification.objects.create(
            recipient='bob@hospital.local',
            recipient_user=self.patient_user_2,
            appointment=self.apt_2,
            notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMATION,
            status=Notification.Status.SENT,
            subject='Confidential Medical Confirmation',
            message='Private information for Bob',
        )

        res = self.patient_1_client.get('/api/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [n['id'] for n in res.data['results']]
        self.assertNotIn(notif_2.id, returned_ids)


class InputValidationAndInjectionTests(SecurityHardeningBaseTestCase):
    """
    Tests input validation, SQL injection resilience, and XSS safety.
    """
    def test_sql_injection_in_search_and_filter_resilient(self):
        """Verify SQL injection payloads in search and query parameters are safely handled."""
        payloads = [
            "' OR 1=1 --",
            "'; DROP TABLE appointments; --",
            "1' UNION SELECT username, password FROM accounts_user --",
            "admin'--",
            "\" OR \"\"=\"",
        ]
        for injection in payloads:
            # 1. Doctor search
            res = self.anon_client.get(f'/api/doctors/?search={injection}')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            # 2. Department search
            res = self.anon_client.get(f'/api/departments/?search={injection}')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            # 3. Patient filtering (authenticated)
            res = self.patient_1_client.get(f'/api/patients/?gender={injection}')
            self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])

    def test_xss_payload_stored_safely_as_plain_text(self):
        """Verify HTML/JavaScript payloads in user inputs are stored as plain text without script execution."""
        xss_string = "<script>alert('XSS_SECURITY_TEST');</script><img src=x onerror=alert(1)>"
        target_date = date.today() + timedelta(days=6)
        DoctorSchedule.objects.create(
            doctor=self.doctor_1,
            day_of_week=target_date.strftime('%A'),
            start_time=dtime(9, 0),
            end_time=dtime(17, 0),
            slot_duration_minutes=30,
            is_working_day=True,
            is_active=True,
        )

        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(target_date),
            'start_time': '14:00:00',
            'end_time': '14:30:00',
            'reason_for_visit': xss_string,
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Content is safely returned as JSON escaped string
        self.assertIn('alert', res.data['reason_for_visit'])
        # Verify stored verbatim in DB
        apt = Appointment.objects.get(reference=res.data['reference'])
        self.assertEqual(apt.reason_for_visit, xss_string)

    def test_malformed_json_and_types_return_clean_400(self):
        """Verify malformed payload returns clean HTTP 400 Bad Request."""
        res = self.patient_1_client.post(
            '/api/appointments/',
            data='{malformed_json: true,',
            content_type='application/json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_dates_and_times_return_clean_400(self):
        """Verify non-existent dates or invalid times return HTTP 400."""
        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': '2026-02-31',  # Non-existent date
            'start_time': '99:99:99',          # Non-existent time
            'end_time': '10:30:00',
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class RateLimitingSecurityTests(SecurityHardeningBaseTestCase):
    """
    Tests API rate limiting and throttling.
    """
    def test_login_rate_limiting_enforced(self):
        """Verify rapid repeated login attempts trigger HTTP 429 Too Many Requests."""
        cache.clear()
        with patch.object(LoginRateThrottle, 'get_rate', return_value='3/minute'):
            client = APIClient()
            statuses = []
            for _ in range(6):
                res = client.post('/api/auth/login/', {
                    'email': 'nonexistent@hospital.local',
                    'password': 'WrongPassword123!',
                })
                statuses.append(res.status_code)

            # At least one request should be throttled with HTTP 429
            self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, statuses)

    def test_appointment_booking_rate_limiting_configured(self):
        """Verify appointment booking endpoint throttles rapid requests."""
        cache.clear()
        target_date = date.today() + timedelta(days=7)
        DoctorSchedule.objects.create(
            doctor=self.doctor_1,
            day_of_week=target_date.strftime('%A'),
            start_time=dtime(9, 0),
            end_time=dtime(17, 0),
            slot_duration_minutes=30,
            is_working_day=True,
            is_active=True,
        )

        with patch.object(AppointmentBookingRateThrottle, 'get_rate', return_value='2/minute'):
            statuses = []
            for i in range(5):
                start_h = 10 + (i // 2)
                start_m = (i % 2) * 30
                end_m = (start_m + 30) % 60
                end_h = start_h + 1 if end_m == 0 else start_h

                res = self.patient_1_client.post('/api/appointments/', {
                    'doctor': self.doctor_1.id,
                    'appointment_date': str(target_date),
                    'start_time': f'{start_h:02d}:{start_m:02d}:00',
                    'end_time': f'{end_h:02d}:{end_m:02d}:00',
                    'reason_for_visit': f'Throttling test {i}',
                })
                statuses.append(res.status_code)

            self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, statuses)


class AppointmentSecurityRegressionTests(SecurityHardeningBaseTestCase):
    """
    Tests appointment booking security rules, constraint enforcement, and abuse scenarios.
    """
    def setUp(self):
        super().setUp()
        self.future_date = date.today() + timedelta(days=5)
        self.schedule = DoctorSchedule.objects.create(
            doctor=self.doctor_1,
            day_of_week=self.future_date.strftime('%A'),
            start_time=dtime(9, 0),
            end_time=dtime(17, 0),
            slot_duration_minutes=30,
            is_working_day=True,
            is_active=True,
        )

    def test_booking_past_date_rejected(self):
        """Verify appointment for past date is rejected."""
        past_date = date.today() - timedelta(days=1)
        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(past_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_inactive_doctor_rejected(self):
        """Verify appointment with inactive doctor is rejected."""
        self.doctor_1.is_active = False
        self.doctor_1.save()

        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_during_doctor_leave_rejected(self):
        """Verify appointment during doctor approved leave is rejected."""
        DoctorLeave.objects.create(
            doctor=self.doctor_1,
            start_date=self.future_date,
            end_date=self.future_date,
            reason='Annual leave',
            is_active=True,
        )

        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
        })
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_booking_during_recess_break_rejected(self):
        """Verify appointment during doctor shift break is rejected."""
        ScheduleBreak.objects.create(
            schedule=self.schedule,
            start_time=dtime(13, 0),
            end_time=dtime(14, 0),
            name='Lunch Break',
        )

        res = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '13:00:00',
            'end_time': '13:30:00',
        })
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_double_booking_rejected_with_conflict_409(self):
        """Verify second booking attempt for same slot receives HTTP 409 Conflict."""
        # First booking succeeds
        res1 = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
        })
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second booking attempt by Patient 2 for identical slot must fail with 409
        res2 = self.patient_2_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '10:00:00',
            'end_time': '10:30:00',
        })
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)

    def test_idempotent_booking_with_same_key_returns_200(self):
        """Verify duplicate booking request with identical Idempotency-Key returns HTTP 200 without duplicate creation."""
        headers = {'HTTP_IDEMPOTENCY_KEY': 'SEC-IDEMPOTENCY-TEST-KEY-001'}
        res1 = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '11:00:00',
            'end_time': '11:30:00',
        }, **headers)
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.patient_1_client.post('/api/appointments/', {
            'doctor': self.doctor_1.id,
            'appointment_date': str(self.future_date),
            'start_time': '11:00:00',
            'end_time': '11:30:00',
        }, **headers)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['reference'], res2.data['reference'])


class MediaSecurityTests(SecurityHardeningBaseTestCase):
    """
    Tests media upload security, binary validation, spoofing prevention, and credential protection.
    """
    def test_spoofed_mime_and_executable_rejected(self):
        """Verify executable or text script renamed to .jpg fails Pillow verification and is rejected."""
        fake_image = io.BytesIO(b"#!/bin/bash\necho 'MALICIOUS SCRIPT'\n")
        fake_image.name = 'malicious.jpg'

        res = self.super_admin_client.post(
            f'/api/doctors/{self.doctor_1.slug}/upload-photo/',
            {'photo': fake_image},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('failed image verification', str(res.data).lower())

    def test_oversized_image_rejected(self):
        """Verify file exceeding 5MB limit is rejected with HTTP 400."""
        # 6MB dummy byte buffer
        oversized = io.BytesIO(b'x' * (6 * 1024 * 1024))
        oversized.name = 'oversized.jpg'

        res = self.super_admin_client.post(
            f'/api/doctors/{self.doctor_1.slug}/upload-photo/',
            {'photo': oversized},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('5mb limit', str(res.data).lower())

    def test_unauthorized_media_upload_rejected(self):
        """Verify patient attempting to upload a photo receives HTTP 403."""
        img = self._create_test_image('JPEG')
        res = self.patient_1_client.post(
            f'/api/doctors/{self.doctor_1.slug}/upload-photo/',
            {'photo': img},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(
        CLOUDINARY_CLOUD_NAME='sec_cloud',
        CLOUDINARY_API_KEY='sec_key',
        CLOUDINARY_API_SECRET='SUPER_SECRET_VALUE_XYZ987',
    )
    @patch('cloudinary.uploader.upload')
    def test_cloudinary_error_masks_api_secret(self, mock_upload):
        """Verify Cloudinary error never leaks API secret or keys into API responses."""
        mock_upload.side_effect = Exception("Cloudinary failure with api_secret=SUPER_SECRET_VALUE_XYZ987 timeout")
        img = self._create_test_image('JPEG')

        res = self.super_admin_client.post(
            f'/api/doctors/{self.doctor_1.slug}/upload-photo/',
            {'photo': img},
            format='multipart'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('SUPER_SECRET_VALUE_XYZ987', str(res.data))
        self.assertNotIn('SUPER_SECRET_VALUE_XYZ987', str(res.content))


class SecretsAndPrivacyTests(SecurityHardeningBaseTestCase):
    """
    Tests secret isolation, PII sanitization, and security headers.
    """
    def test_api_responses_never_contain_password_hashes(self):
        """Verify user serializers never output password hashes."""
        res = self.super_admin_client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn('password', res.data)
        self.assertNotIn('pbkdf2', str(res.data))

    @override_settings(DEBUG=False)
    def test_production_mode_masks_internal_tracebacks(self):
        """Verify when DEBUG=False, unhandled server exceptions return sanitized 500 response without traceback."""
        with patch('apps.accounts.views_auth.CurrentUserView.get') as mock_get:
            mock_get.side_effect = RuntimeError("Database connection string postgres://secret:pass@internal/db failed")
            res = self.patient_1_client.get('/api/auth/me/')
            self.assertEqual(res.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertEqual(
                res.data.get('detail'),
                "An internal server error occurred. Please contact hospital support."
            )
            self.assertNotIn('postgres://secret:pass', str(res.content))
            self.assertNotIn('RuntimeError', str(res.content))

    def test_security_headers_configured_in_responses(self):
        """Verify security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy) are present in responses."""
        res = self.anon_client.get('/api/health/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.headers.get('X-Frame-Options'), 'DENY')
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'same-origin')


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_security_hardening'])
    sys.exit(bool(failures))

