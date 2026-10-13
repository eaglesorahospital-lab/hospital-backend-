"""
Unit tests for secure Hospital Administrator account management and RBAC enforcement.
Verifies account creation, password hashing, role assignment, duplicate email validation,
self-deactivation guards, public registration escalation prevention, and login authorization.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.services import HOSPITAL_ADMIN_GROUP_NAME, get_or_create_hospital_admin_group

User = get_user_model()


class HospitalAdminManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Super Admin user
        self.super_admin = User.objects.create_superuser(
            email='superadmin@hospital.org',
            password='SuperAdminPass123!',
            first_name='Super',
            last_name='Admin',
        )

        # 2. Regular Hospital Admin user
        self.hospital_admin = User.objects.create_user(
            email='hospitaladmin@hospital.org',
            password='HospitalAdminPass123!',
            first_name='Hospital',
            last_name='Manager',
            role=User.Role.HOSPITAL_ADMIN,
            is_staff=True,
            is_active=True,
        )
        group = get_or_create_hospital_admin_group()
        self.hospital_admin.groups.add(group)

        # 3. Regular Doctor Staff user
        self.doctor_staff = User.objects.create_user(
            email='doctor@hospital.org',
            password='DoctorPass123!',
            first_name='Doctor',
            last_name='Staff',
            role=User.Role.DOCTOR_STAFF,
            is_staff=True,
            is_active=True,
        )

        # 4. Outpatient user
        self.patient = User.objects.create_user(
            email='patient@hospital.org',
            password='PatientPass123!',
            first_name='John',
            last_name='Doe',
            role=User.Role.PATIENT,
            is_staff=False,
            is_active=True,
        )

    def test_super_admin_creates_hospital_admin_success(self):
        """
        Verify that an authorized SUPER_ADMIN can create a new Hospital Administrator:
        - Password is cryptographically hashed (never plaintext).
        - Role is set to HOSPITAL_ADMIN.
        - is_staff is True.
        - User is assigned to 'Hospital Administrators' Django group.
        """
        self.client.force_authenticate(user=self.super_admin)

        payload = {
            'full_name': 'Dr. Sunita Rao',
            'email': 'sunita.rao@hospital.org',
            'password': 'SecureAdminPass123!',
            'password_confirm': 'SecureAdminPass123!',
            'phone': '9876543210',
        }

        response = self.client.post('/api/administrators/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        self.assertEqual(data['email'], 'sunita.rao@hospital.org')
        self.assertEqual(data['role'], User.Role.HOSPITAL_ADMIN)
        self.assertTrue(data['is_staff'])
        self.assertTrue(data['is_active'])
        self.assertNotIn('password', data)

        # Verify DB state
        created_user = User.objects.get(email='sunita.rao@hospital.org')
        self.assertEqual(created_user.role, User.Role.HOSPITAL_ADMIN)
        self.assertTrue(created_user.is_staff)
        self.assertTrue(created_user.is_active)
        self.assertEqual(created_user.first_name, 'Dr.')
        self.assertEqual(created_user.last_name, 'Sunita Rao')

        # Verify password is properly hashed
        self.assertNotEqual(created_user.password, 'SecureAdminPass123!')
        self.assertTrue(created_user.check_password('SecureAdminPass123!'))

        # Verify group membership
        group_names = [g.name for g in created_user.groups.all()]
        self.assertIn(HOSPITAL_ADMIN_GROUP_NAME, group_names)

    def test_hospital_admin_cannot_create_administrator(self):
        """
        A regular Hospital Administrator must NOT be able to create administrator accounts (403 Forbidden).
        """
        self.client.force_authenticate(user=self.hospital_admin)

        payload = {
            'full_name': 'Rival Admin',
            'email': 'rival@hospital.org',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
        }

        response = self.client.post('/api/administrators/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(email='rival@hospital.org').exists())

    def test_doctor_staff_and_patient_cannot_create_administrator(self):
        """
        Doctor staff and patients must receive 403 Forbidden when attempting to access /api/administrators/.
        """
        # Doctor staff
        self.client.force_authenticate(user=self.doctor_staff)
        response = self.client.post('/api/administrators/', {'email': 'test@hospital.org'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Patient
        self.client.force_authenticate(user=self.patient)
        response = self.client.post('/api/administrators/', {'email': 'test2@hospital.org'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_or_list_administrators(self):
        """
        Unauthenticated requests must receive 401 Unauthorized.
        """
        response = self.client.get('/api/administrators/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post('/api/administrators/', {'email': 'unauth@hospital.org'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_email_rejected(self):
        """
        Attempting to create an administrator with an already existing email returns 400 Bad Request.
        """
        self.client.force_authenticate(user=self.super_admin)

        # Attempt with existing hospital_admin email (case-insensitive test)
        payload = {
            'full_name': 'Duplicate User',
            'email': 'HOSPITALADMIN@hospital.org',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
        }

        response = self.client.post('/api/administrators/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_password_validation_enforced(self):
        """
        Passwords must match and meet minimum length (>= 8 chars).
        """
        self.client.force_authenticate(user=self.super_admin)

        # Mismatched passwords
        payload_mismatch = {
            'full_name': 'Mismatch Test',
            'email': 'mismatch@hospital.org',
            'password': 'SecurePass123!',
            'password_confirm': 'DifferentPass123!',
        }
        res = self.client.post('/api/administrators/', payload_mismatch, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', res.data)

        # Weak/short password
        payload_short = {
            'full_name': 'Short Pass',
            'email': 'short@hospital.org',
            'password': 'short',
            'password_confirm': 'short',
        }
        res = self.client.post('/api/administrators/', payload_short, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_super_admin_can_toggle_admin_status(self):
        """
        Super admin can deactivate and reactivate a Hospital Administrator account.
        """
        self.client.force_authenticate(user=self.super_admin)

        # Deactivate
        url = f'/api/administrators/{self.hospital_admin.id}/toggle-status/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])

        self.hospital_admin.refresh_from_db()
        self.assertFalse(self.hospital_admin.is_active)

        # Reactivate
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])

        self.hospital_admin.refresh_from_db()
        self.assertTrue(self.hospital_admin.is_active)

    def test_cannot_deactivate_self(self):
        """
        A super admin cannot deactivate their own administrative account.
        """
        self.client.force_authenticate(user=self.super_admin)
        url = f'/api/administrators/{self.super_admin.id}/toggle-status/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_active)

    def test_cannot_deactivate_super_admin(self):
        """
        Super administrators cannot be deactivated via this endpoint.
        """
        other_super = User.objects.create_superuser(
            email='other_super@hospital.org',
            password='PassOtherSuper123!',
        )
        self.client.force_authenticate(user=self.super_admin)
        url = f'/api/administrators/{other_super.id}/toggle-status/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        other_super.refresh_from_db()
        self.assertTrue(other_super.is_active)

    def test_hospital_admin_cannot_toggle_admin_status(self):
        """
        Regular Hospital Administrator cannot deactivate accounts (403 Forbidden).
        """
        self.client.force_authenticate(user=self.hospital_admin)
        url = f'/api/administrators/{self.hospital_admin.id}/toggle-status/'
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_registration_strictly_patient_role(self):
        """
        Verify that public registration endpoint (/api/auth/register/) cannot be exploited
        to create an administrator or staff account.
        """
        public_client = APIClient()
        payload = {
            'email': 'sneaky_patient@hospital.org',
            'password': 'ValidPassword123!',
            'password_confirm': 'ValidPassword123!',
            'first_name': 'Sneaky',
            'last_name': 'User',
            'role': 'SUPER_ADMIN',  # Attempt privilege escalation
            'is_staff': True,
        }
        response = public_client.post('/api/auth/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='sneaky_patient@hospital.org')
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_newly_created_admin_login_and_access_boundaries(self):
        """
        Verify that a newly created Hospital Administrator:
        1. Can log in via /api/auth/login/.
        2. Receives a JWT token containing the HOSPITAL_ADMIN role.
        3. Can access authorized hospital operations (e.g. /api/patients/).
        4. CANNOT access /api/administrators/ (403 Forbidden).
        """
        # Step 1: Super Admin creates the administrator
        self.client.force_authenticate(user=self.super_admin)
        create_payload = {
            'full_name': 'Operational Admin',
            'email': 'ops.admin@hospital.org',
            'password': 'OpsPassword2026!',
            'password_confirm': 'OpsPassword2026!',
        }
        res = self.client.post('/api/administrators/', create_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Step 2: Login via /api/auth/login/
        anon_client = APIClient()
        login_res = anon_client.post('/api/auth/login/', {
            'email': 'ops.admin@hospital.org',
            'password': 'OpsPassword2026!',
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        access_token = login_res.data['access']
        self.assertEqual(login_res.data['user']['role'], User.Role.HOSPITAL_ADMIN)

        # Step 3: Use access token to access authorized operations (/api/patients/)
        auth_client = APIClient()
        auth_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        patients_res = auth_client.get('/api/patients/')
        self.assertEqual(patients_res.status_code, status.HTTP_200_OK)

        # Step 4: Verify access to /api/administrators/ is forbidden
        admin_manage_res = auth_client.get('/api/administrators/')
        self.assertEqual(admin_manage_res.status_code, status.HTTP_403_FORBIDDEN)

        admin_create_res = auth_client.post('/api/administrators/', {
            'email': 'unauthorized@hospital.org'
        }, format='json')
        self.assertEqual(admin_create_res.status_code, status.HTTP_403_FORBIDDEN)


class PatientIdentityAndProfileIsolationTests(TestCase):
    """
    Security and isolation test suite ensuring:
    - Authenticated patient derives identity strictly from JWT context.
    - Patient A sees only Patient A's profile and appointments.
    - Patient B sees only Patient B's profile and appointments.
    - Patient A cannot view, tamper with, or cancel Patient B's records.
    - Unauthenticated callers are rejected with HTTP 401.
    - Account updates persist cleanly in PostgreSQL.
    """
    def setUp(self):
        from apps.accounts.models import PatientProfile
        from apps.departments.models import Department
        from apps.doctors.models import Doctor

        self.client = APIClient()

        # Patient A
        self.user_a = User.objects.create_user(
            email='patient.a@hospital.org',
            password='PatientAPass123!',
            first_name='Alpha',
            last_name='Patient',
            role=User.Role.PATIENT,
        )
        self.profile_a = PatientProfile.objects.create(
            user=self.user_a,
            first_name='Alpha',
            last_name='Patient',
            email='patient.a@hospital.org',
            phone='9111111111',
            address='101 Alpha Blvd',
        )

        # Patient B
        self.user_b = User.objects.create_user(
            email='patient.b@hospital.org',
            password='PatientBPass123!',
            first_name='Beta',
            last_name='Patient',
            role=User.Role.PATIENT,
        )
        self.profile_b = PatientProfile.objects.create(
            user=self.user_b,
            first_name='Beta',
            last_name='Patient',
            email='patient.b@hospital.org',
            phone='9222222222',
            address='202 Beta Way',
        )

        # Department and Doctor
        self.dept = Department.objects.create(
            name='General Medicine',
            slug='general-medicine',
            specialty='Internal Medicine',
            short_description='General OPD',
            full_description='General Medicine Department',
            location='Wing A, 1st Floor',
        )
        self.doctor = Doctor.objects.create(
            name='Dr. Clinic Specialist',
            slug='dr-clinic-specialist',
            department=self.dept,
            qualification='MBBS, MD',
            bio='Consultant Physician',
            consultation_location='Suite 101',
            experience_years=8,
            is_active=True,
        )

    def test_unauthenticated_requests_rejected(self):
        resp = self.client.get('/api/patients/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        resp_list = self.client.get('/api/patients/')
        self.assertEqual(resp_list.status_code, status.HTTP_401_UNAUTHORIZED)

        resp_apts = self.client.get('/api/appointments/')
        self.assertEqual(resp_apts.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_a_sees_only_own_profile(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get('/api/patients/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['id'], self.profile_a.id)
        self.assertEqual(resp.data['email'], 'patient.a@hospital.org')
        self.assertEqual(resp.data['first_name'], 'Alpha')

        # Cannot view Patient B by ID
        resp_b = self.client.get(f'/api/patients/{self.profile_b.id}/')
        self.assertIn(resp_b.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_patient_cannot_tamper_with_other_patient_profile(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.patch(f'/api/patients/{self.profile_b.id}/', {'address': 'Tampered!'})
        self.assertIn(resp.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        self.profile_b.refresh_from_db()
        self.assertEqual(self.profile_b.address, '202 Beta Way')

    def test_patient_can_update_own_profile_via_me(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.patch('/api/patients/me/', {'address': 'Suite 999 New'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.address, 'Suite 999 New')

    def test_appointments_isolation_between_patients(self):
        from apps.appointments.models import Appointment

        apt_a = Appointment.objects.create(
            reference='APT-A-ISO-100',
            patient=self.profile_a,
            doctor=self.doctor,
            department=self.dept,
            appointment_date='2026-11-25',
            start_time='09:00:00',
            end_time='09:30:00',
        )
        apt_b = Appointment.objects.create(
            reference='APT-B-ISO-200',
            patient=self.profile_b,
            doctor=self.doctor,
            department=self.dept,
            appointment_date='2026-11-26',
            start_time='10:00:00',
            end_time='10:30:00',
        )

        # Patient A view
        self.client.force_authenticate(user=self.user_a)
        resp_a = self.client.get('/api/appointments/')
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        refs_a = [a['reference'] for a in resp_a.data.get('results', [])]
        self.assertIn('APT-A-ISO-100', refs_a)
        self.assertNotIn('APT-B-ISO-200', refs_a)

        # Patient A cannot view details of B's appointment
        resp_detail = self.client.get(f'/api/appointments/{apt_b.reference}/')
        self.assertIn(resp_detail.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Patient A cannot cancel B's appointment
        resp_cancel = self.client.post(f'/api/appointments/{apt_b.reference}/cancel/', {'reason': 'Tamper'})
        self.assertIn(resp_cancel.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Patient B view
        self.client.force_authenticate(user=self.user_b)
        resp_b = self.client.get('/api/appointments/')
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        refs_b = [a['reference'] for a in resp_b.data.get('results', [])]
        self.assertIn('APT-B-ISO-200', refs_b)
        self.assertNotIn('APT-A-ISO-100', refs_b)

