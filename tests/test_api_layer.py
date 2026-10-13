"""
Phase 11 REST API Layer Test Suite.
Validates serializers, viewsets, URL routers, pagination, filtering, search,
ordering, validation errors, security constraints, and boundary rules.
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
from apps.hospital.models import HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ
from apps.departments.models import Department, DepartmentService, DepartmentFAQ
from apps.doctors.models import Specialty, Doctor
from apps.scheduling.models import DoctorSchedule, DoctorLeave, ScheduleOverride
from apps.appointments.models import Appointment
from apps.notifications.models import Notification, AuditLog

User = get_user_model()


class APILayerTests(TestCase):
    """Comprehensive test suite for Phase 11 REST APIs."""

    def setUp(self):
        self.client = APIClient()

        # Seed minimal database entities for test execution
        self.hospital = HospitalProfile.objects.create(
            name="EgleSora Test Hospital",
            legal_name="EgleSora Test Legal",
            tagline="Clinical Excellence",
            overview="Tertiary test hospital overview.",
            is_active=True,
        )
        self.facility = HospitalFacility.objects.create(
            name="Intensive Care Unit",
            description="24/7 Tertiary ICU with ECMO.",
            order=1,
            is_active=True,
        )
        self.announcement = HospitalAnnouncement.objects.create(
            title="OPD Advisory",
            slug="opd-advisory",
            summary="OPD timings updated.",
            content="Detailed announcement content.",
            is_published=True,
        )
        self.faq = HospitalFAQ.objects.create(
            question="What are visiting hours?",
            answer="Visiting hours are 08:00 to 20:00.",
            order=1,
            is_active=True,
        )

        self.dept = Department.objects.create(
            name="Cardiology",
            slug="cardiology",
            specialty="Cardiovascular Sciences",
            short_description="Heart and vascular care.",
            full_description="Comprehensive cardiac surgery and intervention.",
            is_active=True,
        )
        self.dept_service = DepartmentService.objects.create(
            department=self.dept,
            name="Echocardiography",
            description="Diagnostic ultrasound of the heart.",
            order=1,
            is_active=True,
        )
        self.dept_faq = DepartmentFAQ.objects.create(
            department=self.dept,
            question="Is fasting required for Echo?",
            answer="No, fasting is not required.",
            order=1,
            is_active=True,
        )

        self.specialty = Specialty.objects.create(
            name="Interventional Cardiology",
            slug="interventional-cardiology",
            description="Catheter-based therapies.",
            is_active=True,
        )
        self.doctor = Doctor.objects.create(
            name="Dr. Marcus Vance",
            slug="dr-marcus-vance",
            department=self.dept,
            specialty=self.specialty,
            qualification="MD, DM (Cardiology)",
            experience_years=14,
            bio="Senior consultant in interventional cardiology.",
            expertise="Coronary angioplasty, TAVI",
            consultation_type="In-person Consultation",
            consultation_duration_minutes=30,
            consultation_location="Wing B, Suite 204",
            is_active=True,
        )

        self.user = User.objects.create_user(
            email="patient.test@example.com",
            first_name="Jane",
            last_name="Doe",
            phone="+919876543210",
        )
        self.patient = PatientProfile.objects.create(
            user=self.user,
            mrn="MRN-TEST-1001",
            first_name="Jane",
            last_name="Doe",
            date_of_birth=date(1990, 5, 15),
            gender=PatientProfile.Gender.FEMALE,
            phone="+919876543210",
            email="patient.test@example.com",
            is_active=True,
        )

        for day in DoctorSchedule.DayOfWeek.values:
            DoctorSchedule.objects.get_or_create(
                doctor=self.doctor,
                day_of_week=day,
                defaults={
                    "start_time": time(9, 0),
                    "end_time": time(17, 0),
                    "slot_duration_minutes": 30,
                    "capacity": 1,
                    "timezone": "Asia/Kolkata",
                    "is_working_day": True,
                    "is_active": True,
                }
            )
        self.schedule = DoctorSchedule.objects.get(
            doctor=self.doctor,
            day_of_week=DoctorSchedule.DayOfWeek.MONDAY,
        )

        self.appointment = Appointment.objects.create(
            reference="APT-2026-TEST01",
            patient=self.patient,
            doctor=self.doctor,
            department=self.dept,
            appointment_date=date.today() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(10, 30),
            appointment_type=Appointment.AppointmentType.IN_PERSON,
            status=Appointment.Status.CONFIRMED,
            reason_for_visit="Routine cardiac checkup.",
        )

        self.notification = Notification.objects.create(
            recipient=self.patient.email,
            recipient_user=self.user,
            appointment=self.appointment,
            notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMATION,
            channel=Notification.Channel.EMAIL,
            status=Notification.Status.SENT,
            subject="Appointment Confirmed",
            message="Your appointment is confirmed.",
        )

        self.audit = AuditLog.objects.create(
            actor=self.user,
            actor_name="Jane Doe",
            role="PATIENT",
            action="APPOINTMENT_BOOKED",
            resource_type="Appointment",
            resource_id="APT-2026-TEST01",
            result=AuditLog.Result.SUCCESS,
            details="Patient booked consultation.",
        )

        self.admin_user = User.objects.create_superuser(
            email="admin.api@eglesora.org",
            password="AdminPass123!",
            first_name="Admin",
            last_name="Tester",
        )
        refresh = RefreshToken.for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    # 1. API Root
    def test_api_root_endpoint(self):
        res = self.client.get('/api/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data.get('service'), 'hospital-platform-api')
        self.assertIn('hospital', data.get('endpoints', {}))
        self.assertIn('doctors', data.get('endpoints', {}))
        self.assertIn('appointments', data.get('endpoints', {}))

    # 2. Health Endpoint
    def test_health_check_endpoint(self):
        res = self.client.get('/api/health/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('status'), 'ok')

    # 3. Hospital Endpoints
    def test_hospital_profile_current_and_facilities(self):
        res = self.client.get('/api/hospital/current/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('name'), 'EgleSora Test Hospital')

        res_fac = self.client.get('/api/hospital/facilities/')
        self.assertEqual(res_fac.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_fac.json().get('count', 0), 1)

    def test_hospital_announcements_and_faqs(self):
        res_ann = self.client.get('/api/hospital/announcements/')
        self.assertEqual(res_ann.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_ann.json().get('count', 0), 1)

        res_faq = self.client.get('/api/hospital/faqs/')
        self.assertEqual(res_faq.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_faq.json().get('count', 0), 1)

    # 4. Department Endpoints
    def test_department_list_detail_and_actions(self):
        res_list = self.client.get('/api/departments/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_list.json().get('count', 0), 1)

        res_detail = self.client.get('/api/departments/cardiology/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.json().get('name'), 'Cardiology')
        self.assertIn('services', res_detail.json())
        self.assertIn('faqs', res_detail.json())

        # Test sub-actions
        res_serv = self.client.get('/api/departments/cardiology/services/')
        self.assertEqual(res_serv.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_serv.json()), 1)

        res_faqs = self.client.get('/api/departments/cardiology/faqs/')
        self.assertEqual(res_faqs.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res_faqs.json()), 1)

    # 5. Specialty Endpoints
    def test_specialty_list(self):
        res = self.client.get('/api/specialties/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.json().get('count', 0), 1)

    # 6. Doctor List and Detail
    def test_doctor_list_and_detail(self):
        res_list = self.client.get('/api/doctors/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_list.json().get('count', 0), 1)

        res_detail = self.client.get('/api/doctors/dr-marcus-vance/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        data = res_detail.json()
        self.assertEqual(data.get('name'), 'Dr. Marcus Vance')
        self.assertEqual(data.get('qualification'), 'MD, DM (Cardiology)')
        self.assertIn('department_detail', data)

    # 7. Doctor Filtering
    def test_doctor_filtering(self):
        res = self.client.get(f'/api/doctors/?department={self.dept.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('count'), 1)

        res_none = self.client.get('/api/doctors/?specialty__slug=non-existent-specialty')
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertEqual(res_none.json().get('count'), 0)

    # 8. Schedule Endpoints
    def test_schedules_list_and_filters(self):
        res = self.client.get(f'/api/schedules/?doctor={self.doctor.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.json().get('count', 0), 1)

    # 9 & 10. Appointment List and Detail
    def test_appointment_list_and_detail(self):
        res_list = self.client.get('/api/appointments/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_list.json().get('count', 0), 1)

        res_detail = self.client.get(f'/api/appointments/{self.appointment.reference}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.json().get('reference'), self.appointment.reference)

    # 11. Appointment Create Validation
    def test_appointment_create_valid_and_invalid(self):
        # Valid create
        valid_payload = {
            "patient": self.patient.id,
            "doctor": self.doctor.id,
            "appointment_date": str(date.today() + timedelta(days=5)),
            "start_time": "11:00:00",
            "end_time": "11:30:00",
            "appointment_type": "IN_PERSON",
            "status": "CONFIRMED",
            "reason_for_visit": "Test consultation.",
        }
        res_create = self.client.post('/api/appointments/', valid_payload, format='json')
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        created_ref = res_create.json().get('reference')
        self.assertTrue(created_ref.startswith('APT-'))

        # Invalid create: end_time before start_time
        invalid_payload = valid_payload.copy()
        invalid_payload["start_time"] = "12:00:00"
        invalid_payload["end_time"] = "11:00:00"
        res_invalid = self.client.post('/api/appointments/', invalid_payload, format='json')
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_time', res_invalid.json())

    # 12. Appointment Filtering
    def test_appointment_filtering(self):
        res_filter = self.client.get('/api/appointments/?status=CONFIRMED')
        self.assertEqual(res_filter.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_filter.json().get('count', 0), 1)

        res_wrong = self.client.get('/api/appointments/?status=CANCELLED')
        self.assertEqual(res_wrong.status_code, status.HTTP_200_OK)
        self.assertEqual(res_wrong.json().get('count'), 0)

    # 13. Patient Endpoints
    def test_patient_list_and_detail(self):
        res_list = self.client.get('/api/patients/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_list.json().get('count', 0), 1)

        res_detail = self.client.get(f'/api/patients/{self.patient.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.json().get('mrn'), self.patient.mrn)

    # 14. Notification Endpoint
    def test_notification_list_and_detail(self):
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.json().get('count', 0), 1)

    # 15. Audit Endpoint (Read-Only)
    def test_audit_list_and_read_only_enforcement(self):
        res_get = self.client.get('/api/audit/')
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_get.json().get('count', 0), 1)

        # POST should be rejected with 405 Method Not Allowed
        res_post = self.client.post('/api/audit/', {"action": "HACK"}, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # 16. Pagination Metadata
    def test_pagination_structure(self):
        res = self.client.get('/api/doctors/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn('count', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIn('results', data)
        self.assertIsInstance(data['results'], list)

    # 17. Search Functionality
    def test_search_filtering(self):
        res = self.client.get('/api/doctors/?search=Marcus')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json().get('count'), 1)

        res_none = self.client.get('/api/doctors/?search=NonExistentDoctorName')
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertEqual(res_none.json().get('count'), 0)

    # 18. Ordering Functionality
    def test_ordering(self):
        res_asc = self.client.get('/api/doctors/?ordering=name')
        self.assertEqual(res_asc.status_code, status.HTTP_200_OK)
        res_desc = self.client.get('/api/doctors/?ordering=-name')
        self.assertEqual(res_desc.status_code, status.HTTP_200_OK)

    # 19. Invalid Request Handling
    def test_invalid_request_handling(self):
        res = self.client.post('/api/appointments/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        data = res.json()
        self.assertIn('patient', data)
        self.assertIn('doctor', data)

    # 20. 404 Error Handling
    def test_not_found_handling(self):
        res_dept = self.client.get('/api/departments/non-existent-slug/')
        self.assertEqual(res_dept.status_code, status.HTTP_404_NOT_FOUND)

        res_doc = self.client.get('/api/doctors/non-existent-slug/')
        self.assertEqual(res_doc.status_code, status.HTTP_404_NOT_FOUND)

        res_apt = self.client.get('/api/appointments/APT-9999-DOESNOTEXIST/')
        self.assertEqual(res_apt.status_code, status.HTTP_404_NOT_FOUND)

    # 21. Security Verification
    def test_security_sanitization_no_credentials_leaked(self):
        res = self.client.get(f'/api/patients/{self.patient.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        raw_text = str(data)
        self.assertNotIn('password', raw_text.lower())
        self.assertNotIn('pbkdf2', raw_text.lower())
        self.assertNotIn('secret', raw_text.lower())


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_api_layer'])
    sys.exit(bool(failures))
