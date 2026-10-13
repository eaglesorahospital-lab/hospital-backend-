"""
Domain model tests for Hospital Platform (Phase 10).
Validates model definitions, choices, validation rules (clean), reference generators,
and boundary integrity across Accounts, Hospital, Departments, Doctors, Scheduling,
Appointments, and Notifications modules.
Uses SimpleTestCase (databases = []) for isolated, fast execution.
"""

import os
import sys
from datetime import date, time, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = (ROOT_DIR / 'backend') if (ROOT_DIR / 'backend').exists() else ROOT_DIR

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import SimpleTestCase
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.apps import apps

# Import domain models
from apps.accounts.models import User, PatientProfile
from apps.hospital.models import HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ
from apps.departments.models import Department, DepartmentService, DepartmentFAQ
from apps.doctors.models import Doctor, Specialty
from apps.scheduling.models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
from apps.appointments.models import Appointment, generate_appointment_reference
from apps.notifications.models import Notification, AuditLog


class AccountsModelTests(SimpleTestCase):
    databases = []

    def test_user_roles_defined(self):
        """Verify User model has required PDF roles."""
        expected_roles = {'SUPER_ADMIN', 'HOSPITAL_ADMIN', 'DOCTOR_STAFF', 'PATIENT'}
        actual_roles = {choice[0] for choice in User.Role.choices}
        self.assertEqual(expected_roles, actual_roles)

    def test_user_username_field(self):
        """Verify User model uses email as primary login identifier."""
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_user_str_representation(self):
        """Verify User string output formatting."""
        user = User(email='doctor@eglesora.org', first_name='Rajesh', last_name='Varma', role=User.Role.DOCTOR_STAFF)
        self.assertIn('Rajesh Varma', str(user))
        self.assertIn('doctor@eglesora.org', str(user))

    def test_patient_profile_gender_and_blood_group_choices(self):
        """Verify PatientProfile choices."""
        genders = {c[0] for c in PatientProfile.Gender.choices}
        self.assertEqual(genders, {'MALE', 'FEMALE', 'OTHER'})

        blood_groups = {c[0] for c in PatientProfile.BloodGroup.choices}
        self.assertIn('B+', blood_groups)
        self.assertIn('O+', blood_groups)

    def test_patient_profile_full_name(self):
        """Verify patient full_name property."""
        patient = PatientProfile(first_name='Aarav', last_name='Mehta', mrn='MRN-2026-4401')
        self.assertEqual(patient.full_name, 'Aarav Mehta')
        self.assertIn('MRN-2026-4401', str(patient))


class HospitalModelTests(SimpleTestCase):
    databases = []

    def test_hospital_profile_defaults(self):
        """Verify HospitalProfile metadata defaults."""
        profile = HospitalProfile()
        self.assertEqual(profile.name, 'EgleSora Hospital')
        self.assertTrue(profile.contact_phone)
        self.assertTrue(profile.emergency_phone)

    def test_announcement_slug_generation(self):
        """Verify HospitalAnnouncement slug auto-generation on save."""
        announcement = HospitalAnnouncement(title='Seasonal Advisory 2026')
        with patch('django.db.models.Model.save'):
            announcement.save()
        self.assertEqual(announcement.slug, 'seasonal-advisory-2026')

    def test_hospital_faq_str(self):
        """Verify HospitalFAQ string format."""
        faq = HospitalFAQ(question='Where is the trauma bay?')
        self.assertEqual(str(faq), 'Where is the trauma bay?')


class DepartmentModelTests(SimpleTestCase):
    databases = []

    def test_department_slug_generation(self):
        """Verify Department slug auto-generation."""
        dept = Department(name='Cardiology & Vascular Medicine', specialty='Cardiovascular Care')
        with patch('django.db.models.Model.save'):
            dept.save()
        self.assertEqual(dept.slug, 'cardiology-vascular-medicine')

    def test_department_service_str(self):
        """Verify DepartmentService string format."""
        dept = Department(name='Neurology')
        service = DepartmentService(department=dept, name='EEG Diagnostics')
        self.assertIn('EEG Diagnostics', str(service))
        self.assertIn('Neurology', str(service))


class DoctorModelTests(SimpleTestCase):
    databases = []

    def test_specialty_slug_generation(self):
        """Verify Specialty slug auto-generation."""
        spec = Specialty(name='Pediatric Cardiology')
        with patch('django.db.models.Model.save'):
            spec.save()
        self.assertEqual(spec.slug, 'pediatric-cardiology')

    def test_doctor_slug_and_consultation_defaults(self):
        """Verify Doctor defaults and slug generation."""
        dept = Department(name='Orthopedics')
        doctor = Doctor(
            name='Dr. Vikramaditya Joshi',
            department=dept,
            qualification='MBBS, MS (Ortho)',
            experience_years=14,
        )
        with patch('django.db.models.Model.save'):
            doctor.save()
        self.assertEqual(doctor.slug, 'dr-vikramaditya-joshi')
        self.assertEqual(doctor.consultation_duration_minutes, 30)
        self.assertTrue(doctor.is_active)


class SchedulingModelTests(SimpleTestCase):
    databases = []

    def test_doctor_schedule_clean_validation(self):
        """Verify clean() raises ValidationError when shift end_time is not after start_time."""
        doctor = Doctor(name='Dr. Test')
        schedule = DoctorSchedule(
            doctor=doctor,
            day_of_week='Monday',
            start_time=time(13, 0),
            end_time=time(9, 0),  # Invalid: end before start
        )
        with self.assertRaises(ValidationError):
            schedule.clean()

    def test_schedule_break_clean_validation(self):
        """Verify clean() raises ValidationError when break end_time <= start_time."""
        schedule = DoctorSchedule(start_time=time(9, 0), end_time=time(17, 0))
        brk = ScheduleBreak(
            schedule=schedule,
            start_time=time(13, 0),
            end_time=time(12, 30),  # Invalid
        )
        with self.assertRaises(ValidationError):
            brk.clean()

    def test_doctor_leave_clean_validation(self):
        """Verify clean() raises ValidationError when leave end_date < start_date."""
        doctor = Doctor(name='Dr. Test')
        leave = DoctorLeave(
            doctor=doctor,
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 10),  # Invalid
            reason='Conference',
        )
        with self.assertRaises(ValidationError):
            leave.clean()

    def test_schedule_override_clean_validation(self):
        """Verify clean() raises ValidationError when available override has invalid times."""
        doctor = Doctor(name='Dr. Test')
        override = ScheduleOverride(
            doctor=doctor,
            override_date=date(2026, 11, 28),
            is_available=True,
            start_time=time(15, 0),
            end_time=time(10, 0),  # Invalid
        )
        with self.assertRaises(ValidationError):
            override.clean()


class AppointmentModelTests(SimpleTestCase):
    databases = []

    def test_appointment_statuses_match_pdf(self):
        """Verify appointment statuses strictly follow the PDF requirements."""
        expected_statuses = {
            'REQUESTED',
            'CONFIRMED',
            'CHECKED_IN',
            'COMPLETED',
            'CANCELLED',
            'NO_SHOW',
            'RESCHEDULED',
        }
        actual_statuses = {c[0] for c in Appointment.Status.choices}
        self.assertEqual(expected_statuses, actual_statuses)

    def test_generate_appointment_reference(self):
        """Verify generated reference format."""
        ref = generate_appointment_reference()
        self.assertTrue(ref.startswith('APT-'))
        self.assertIn(str(date.today().year), ref)
        self.assertTrue(len(ref) >= 12)

    def test_appointment_clean_validation(self):
        """Verify clean() raises ValidationError when end_time <= start_time."""
        appointment = Appointment(
            appointment_date=date(2026, 11, 9),
            start_time=time(11, 0),
            end_time=time(10, 0),  # Invalid
        )
        with self.assertRaises(ValidationError):
            appointment.clean()


class NotificationAndAuditModelTests(SimpleTestCase):
    databases = []

    def test_notification_types_and_statuses(self):
        """Verify notification categories and channels."""
        types = {c[0] for c in Notification.NotificationType.choices}
        expected_types = {
            'APPOINTMENT_CONFIRMATION',
            'APPOINTMENT_REMINDER',
            'APPOINTMENT_CANCELLATION',
            'APPOINTMENT_RESCHEDULE',
            'ADMIN_ALERT',
        }
        self.assertEqual(types, expected_types)

        channels = {c[0] for c in Notification.Channel.choices}
        self.assertEqual(channels, {'EMAIL', 'SMS', 'SYSTEM'})

        statuses = {c[0] for c in Notification.Status.choices}
        self.assertEqual(statuses, {'PENDING', 'SENT', 'FAILED'})

    def test_audit_log_results(self):
        """Verify AuditLog result choices."""
        results = {c[0] for c in AuditLog.Result.choices}
        self.assertEqual(results, {'SUCCESS', 'WARNING', 'DENIED'})


class Phase14BoundaryIntegrityTests(SimpleTestCase):
    databases = []

    def test_serializers_and_views_exist_in_domain_apps(self):
        """Verify Phase 14: Serializers and API views exist across all 7 domain apps."""
        for app in ['accounts', 'hospital', 'departments', 'doctors', 'scheduling', 'appointments', 'notifications']:
            app_dir = BACKEND_DIR / 'apps' / app
            serializer_file = app_dir / 'serializers.py'
            views_file = app_dir / 'views.py'
            self.assertTrue(
                serializer_file.exists(),
                f"Missing serializers in {serializer_file}."
            )
            self.assertTrue(
                views_file.exists(),
                f"Missing views in {views_file}."
            )

    def test_notifications_celery_tasks_exist_in_phase_14(self):
        """Verify Phase 14: Celery notification tasks exist in notifications app."""
        tasks_file = BACKEND_DIR / 'apps' / 'notifications' / 'tasks.py'
        self.assertTrue(
            tasks_file.exists(),
            f"Celery tasks missing in {tasks_file} for Phase 14."
        )


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_domain_models'])
    sys.exit(bool(failures))
