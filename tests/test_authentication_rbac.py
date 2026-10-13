"""
Phase 12 JWT Authentication, User Roles, and Role-Based Access Control (RBAC) Test Suite.
Validates registration, login, token refresh, logout/blacklist, current user (/me),
role permissions, object-level access isolation, 401/403 behaviors, and security constraints.
"""

import os
import sys
from pathlib import Path
from datetime import date, time, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PatientProfile
from apps.hospital.models import HospitalProfile
from apps.departments.models import Department
from apps.doctors.models import Doctor, Specialty
from apps.scheduling.models import DoctorSchedule
from apps.appointments.models import Appointment
from apps.notifications.models import AuditLog

User = get_user_model()


class AuthenticationRBACTests(TestCase):
    """Test suite for Phase 12 Authentication and RBAC."""

    def setUp(self):
        self.client = APIClient()

        # Seed roles
        self.super_admin = User.objects.create_superuser(
            email="superadmin@eglesora.org",
            password="AdminPassword123!",
            first_name="Super",
            last_name="Admin",
        )

        self.hospital_admin = User.objects.create_user(
            email="hospadmin@eglesora.org",
            password="HospAdminPass123!",
            first_name="Hospital",
            last_name="Administrator",
            role=User.Role.HOSPITAL_ADMIN,
        )

        self.doctor_user = User.objects.create_user(
            email="doctor@eglesora.org",
            password="DoctorPass123!",
            first_name="Dr. Marcus",
            last_name="Vance",
            role=User.Role.DOCTOR_STAFF,
        )

        self.patient_user_1 = User.objects.create_user(
            email="patient1@example.com",
            password="PatientPass123!",
            first_name="Alice",
            last_name="Smith",
            role=User.Role.PATIENT,
        )
        self.patient_profile_1 = PatientProfile.objects.create(
            user=self.patient_user_1,
            mrn="MRN-TEST-P1",
            first_name="Alice",
            last_name="Smith",
            date_of_birth=date(1992, 3, 10),
            gender=PatientProfile.Gender.FEMALE,
            phone="+919876543211",
            email="patient1@example.com",
            is_active=True,
        )

        self.patient_user_2 = User.objects.create_user(
            email="patient2@example.com",
            password="PatientPass123!",
            first_name="Bob",
            last_name="Jones",
            role=User.Role.PATIENT,
        )
        self.patient_profile_2 = PatientProfile.objects.create(
            user=self.patient_user_2,
            mrn="MRN-TEST-P2",
            first_name="Bob",
            last_name="Jones",
            date_of_birth=date(1985, 7, 22),
            gender=PatientProfile.Gender.MALE,
            phone="+919876543212",
            email="patient2@example.com",
            is_active=True,
        )

        # Hospital domain data
        self.hospital = HospitalProfile.objects.create(
            name="EgleSora Hospital",
            overview="Tertiary healthcare facility.",
            is_active=True,
        )
        self.dept = Department.objects.create(
            name="Cardiology",
            slug="cardiology",
            specialty="Cardiac Care",
            is_active=True,
        )
        self.specialty = Specialty.objects.create(
            name="Cardiology",
            slug="cardiology",
            is_active=True,
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            name="Dr. Marcus Vance",
            slug="dr-marcus-vance",
            department=self.dept,
            specialty=self.specialty,
            qualification="MD",
            is_active=True,
        )

        # Appointment for Patient 1
        self.appointment_1 = Appointment.objects.create(
            reference="APT-2026-ALICE01",
            patient=self.patient_profile_1,
            doctor=self.doctor,
            department=self.dept,
            appointment_date=date.today() + timedelta(days=3),
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.CONFIRMED,
        )

        # Appointment for Patient 2
        self.appointment_2 = Appointment.objects.create(
            reference="APT-2026-BOB0002",
            patient=self.patient_profile_2,
            doctor=self.doctor,
            department=self.dept,
            appointment_date=date.today() + timedelta(days=4),
            start_time=time(11, 0),
            end_time=time(11, 30),
            status=Appointment.Status.CONFIRMED,
        )

        # Audit log entry
        self.audit = AuditLog.objects.create(
            actor=self.super_admin,
            actor_name="Super Admin",
            role="SUPER_ADMIN",
            action="SYSTEM_INIT",
            resource_type="System",
            resource_id="1",
            result=AuditLog.Result.SUCCESS,
        )

    def _get_token(self, user):
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        refresh['email'] = user.email
        return str(refresh.access_token), str(refresh)

    def _authenticate(self, user):
        access_token, _ = self._get_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    # 1. Successful patient registration
    def test_successful_patient_registration(self):
        payload = {
            "email": "newpatient@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "first_name": "Charlie",
            "last_name": "Brown",
            "phone": "+919876543299",
            "date_of_birth": "1994-11-20",
            "gender": "MALE",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertEqual(data['user']['role'], User.Role.PATIENT)
        self.assertEqual(data['user']['email'], "newpatient@example.com")
        self.assertIsNotNone(data['user'].get('mrn'))

        # Verify linked PatientProfile was automatically created
        new_user = User.objects.get(email="newpatient@example.com")
        self.assertTrue(hasattr(new_user, 'patient_profile'))
        self.assertEqual(new_user.patient_profile.first_name, "Charlie")
        self.assertEqual(new_user.patient_profile.mrn, data['user']['mrn'])

    def test_patient_registration_with_empty_dob_and_lowercase_gender(self):
        payload = {
            "email": "empty_dob_patient@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "first_name": "Diana",
            "last_name": "Prince",
            "date_of_birth": "",
            "gender": "female",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['user']['role'], User.Role.PATIENT)
        new_user = User.objects.get(email="empty_dob_patient@example.com")
        self.assertIsNone(new_user.patient_profile.date_of_birth)
        self.assertEqual(new_user.patient_profile.gender, "FEMALE")

    def test_case_insensitive_duplicate_email_registration_rejected(self):
        payload = {
            "email": "PATIENT1@EXAMPLE.COM",  # Uppercase of existing patient1@example.com
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', res.json())

    # 2. Duplicate email rejection
    def test_duplicate_email_registration_rejected(self):
        payload = {
            "email": "patient1@example.com",  # Already exists
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', res.json())

    # 3. Weak password rejection
    def test_weak_password_registration_rejected(self):
        payload = {
            "email": "weakpass@example.com",
            "password": "123",  # Too short / common
            "password_confirm": "123",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', res.json())

    # 4. Password confirmation mismatch
    def test_password_mismatch_registration_rejected(self):
        payload = {
            "email": "mismatch@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "DifferentPassword123!",
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', res.json())

    # 5. Successful login
    def test_successful_login(self):
        payload = {
            "email": "patient1@example.com",
            "password": "PatientPass123!",
        }
        res = self.client.post('/api/auth/login/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertEqual(data['user']['email'], "patient1@example.com")
        self.assertEqual(data['user']['role'], User.Role.PATIENT)

    # 6. Invalid password rejection
    def test_invalid_password_login_rejected(self):
        payload = {
            "email": "patient1@example.com",
            "password": "WrongPassword123!",
        }
        res = self.client.post('/api/auth/login/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', res.json())

    # 7. Invalid credentials response (no leakage of whether user exists)
    def test_nonexistent_email_login_returns_generic_error(self):
        payload = {
            "email": "ghost.user@nonexistent.org",
            "password": "SomePassword123!",
        }
        res = self.client.post('/api/auth/login/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        detail = res.json().get('detail')
        if isinstance(detail, list):
            self.assertIn("Invalid email or password.", detail)
        else:
            self.assertEqual(detail, "Invalid email or password.")

    # 8. Access token generated and valid
    def test_access_token_usage_on_protected_endpoint(self):
        self._authenticate(self.patient_user_1)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('email'), "patient1@example.com")

    # 9. Refresh token works to obtain new access token
    def test_token_refresh_endpoint(self):
        _, refresh_token = self._get_token(self.patient_user_1)
        res = self.client.post('/api/auth/refresh/', {"refresh": refresh_token}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.json())

    # 10. /api/auth/me/ requires authentication (401 when anonymous)
    def test_current_user_unauthenticated_returns_401(self):
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # 11. /api/auth/me/ returns sanitized data
    def test_current_user_returns_sanitized_profile(self):
        self._authenticate(self.patient_user_1)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data.get('email'), "patient1@example.com")
        self.assertEqual(data.get('role'), User.Role.PATIENT)
        self.assertIn('patient_profile', data)
        self.assertEqual(data['patient_profile']['mrn'], "MRN-TEST-P1")
        # Ensure password is not present
        self.assertNotIn('password', str(data).lower())

    # 12. Logout invalidates refresh token via blacklist
    def test_logout_blacklists_refresh_token(self):
        self._authenticate(self.patient_user_1)
        _, refresh_token = self._get_token(self.patient_user_1)

        # Logout
        res_logout = self.client.post('/api/auth/logout/', {"refresh": refresh_token}, format='json')
        self.assertEqual(res_logout.status_code, status.HTTP_200_OK)
        self.assertEqual(res_logout.json().get('detail'), "Successfully logged out.")

        # Attempting to refresh with the blacklisted token must now fail
        res_refresh = self.client.post('/api/auth/refresh/', {"refresh": refresh_token}, format='json')
        self.assertEqual(res_refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    # 13. Public endpoint accessibility
    def test_public_endpoints_accessible_anonymously(self):
        res_hosp = self.client.get('/api/hospital/current/')
        self.assertEqual(res_hosp.status_code, status.HTTP_200_OK)

        res_dept = self.client.get('/api/departments/')
        self.assertEqual(res_dept.status_code, status.HTTP_200_OK)

        res_doc = self.client.get('/api/doctors/')
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)

    # 14. Protected endpoint rejects anonymous user (401)
    def test_protected_endpoints_reject_anonymous_user(self):
        self.assertEqual(self.client.get('/api/appointments/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get('/api/patients/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get('/api/audit/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get('/api/notifications/').status_code, status.HTTP_401_UNAUTHORIZED)

    # 15. Patient role access (can list own appointments)
    def test_patient_can_view_own_appointments(self):
        self._authenticate(self.patient_user_1)
        res = self.client.get('/api/appointments/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json().get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['reference'], "APT-2026-ALICE01")

    # 16. Admin role access (can view all appointments and audit logs)
    def test_admin_can_view_all_appointments_and_audit(self):
        self._authenticate(self.super_admin)
        res_apt = self.client.get('/api/appointments/')
        self.assertEqual(res_apt.status_code, status.HTTP_200_OK)
        self.assertEqual(res_apt.json().get('count'), 2)  # Alice and Bob

        res_audit = self.client.get('/api/audit/')
        self.assertEqual(res_audit.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_audit.json().get('count'), 1)

    # 17. Doctor staff role access
    def test_doctor_staff_operational_access(self):
        self._authenticate(self.doctor_user)
        res = self.client.get('/api/appointments/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.json().get('count'), 1)

    # 18. Patient cannot access another patient's data (object-level isolation)
    def test_patient_cannot_access_other_patient_data(self):
        self._authenticate(self.patient_user_1)

        # Alice attempts to view Bob's appointment by reference
        res_other_apt = self.client.get('/api/appointments/APT-2026-BOB0002/')
        self.assertEqual(res_other_apt.status_code, status.HTTP_404_NOT_FOUND)

        # Alice attempts to view Bob's patient profile
        res_other_profile = self.client.get(f'/api/patients/{self.patient_profile_2.id}/')
        self.assertEqual(res_other_profile.status_code, status.HTTP_404_NOT_FOUND)

    # 19. Patient cannot access administrative endpoints (403 Forbidden)
    def test_patient_cannot_access_admin_endpoints(self):
        self._authenticate(self.patient_user_1)

        # Attempt to access audit logs
        res_audit = self.client.get('/api/audit/')
        self.assertEqual(res_audit.status_code, status.HTTP_403_FORBIDDEN)

        # Attempt to modify doctor schedule leaves
        res_leave = self.client.post('/api/schedules/leaves/', {"doctor": self.doctor.id}, format='json')
        self.assertEqual(res_leave.status_code, status.HTTP_403_FORBIDDEN)

    # 20. Privileged role cannot be selected during registration
    def test_role_escalation_impossible_in_registration(self):
        payload = {
            "email": "hacker@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "role": "SUPER_ADMIN",  # Attempt privilege escalation
        }
        res = self.client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="hacker@example.com")
        self.assertEqual(created_user.role, User.Role.PATIENT)
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)

    # 21. Password hash is never returned in API responses
    def test_password_hash_never_exposed(self):
        self._authenticate(self.patient_user_1)
        res_me = self.client.get('/api/auth/me/')
        self.assertNotIn('pbkdf2', str(res_me.json()).lower())
        self.assertNotIn('password', str(res_me.json()).lower())

        res_patients = self.client.get(f'/api/patients/{self.patient_profile_1.id}/')
        self.assertNotIn('pbkdf2', str(res_patients.json()).lower())
        self.assertNotIn('password', str(res_patients.json()).lower())

    # 22. JWT authentication works against PostgreSQL-backed users
    def test_jwt_auth_against_postgresql(self):
        # Verify directly that JWT authentication establishes correct request.user from PostgreSQL
        self._authenticate(self.hospital_admin)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('role'), User.Role.HOSPITAL_ADMIN)

    # 23. 401 behavior on unauthenticated protected requests
    def test_401_behavior_for_invalid_bearer_token(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid_or_forged_token')
        res = self.client.get('/api/appointments/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # 24. 403 behavior on authenticated but unauthorized requests
    def test_403_behavior_for_insufficient_role(self):
        self._authenticate(self.patient_user_1)
        res = self.client.get('/api/audit/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_authentication_rbac'])
    sys.exit(bool(failures))
