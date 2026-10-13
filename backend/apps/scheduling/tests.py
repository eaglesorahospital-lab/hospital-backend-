import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.doctors.models import Doctor, Specialty
from apps.departments.models import Department
from .models import ScheduleOverride
from .serializers import ScheduleOverrideSerializer

User = get_user_model()


class ScheduleOverrideTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin_user = User.objects.create_user(
            email='admin.test@hospital.org',
            password='TestPassword123!',
            role=User.Role.HOSPITAL_ADMIN,
            is_staff=True,
        )

        # Department & Doctor
        self.dept = Department.objects.create(
            name='Cardiology',
            slug='cardiology',
            specialty='Cardiovascular Care',
            short_description='Heart and vascular clinic',
            full_description='Comprehensive heart and vascular medical care division',
            location='Wing B, 2nd Floor',
        )
        self.specialty = Specialty.objects.create(
            name='Interventional Cardiology',
            slug='interventional-cardiology',
        )
        self.doctor = Doctor.objects.create(
            name='Dr. Test Physician',
            slug='dr-test-physician',
            department=self.dept,
            specialty=self.specialty,
            qualification='MBBS, MD',
            bio='Experienced physician',
            consultation_location='Suite 101',
            experience_years=10,
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin_user)

    def test_create_all_four_override_types_via_serializer(self):
        today = datetime.date.today()

        types_to_test = [
            (ScheduleOverride.OverrideType.SPECIAL_OPD, '08:00:00', '12:00:00', True),
            (ScheduleOverride.OverrideType.EXTENDED_HOURS, '08:00:00', '18:00:00', True),
            (ScheduleOverride.OverrideType.REDUCED_HOURS, '10:00:00', '12:00:00', True),
            (ScheduleOverride.OverrideType.CLOSED, None, None, False),
        ]

        for idx, (override_type, start_t, end_t, expected_available) in enumerate(types_to_test):
            date_val = today + datetime.timedelta(days=idx + 1)
            serializer = ScheduleOverrideSerializer(data={
                'doctor': self.doctor.id,
                'override_date': str(date_val),
                'override_type': override_type,
                'start_time': start_t,
                'end_time': end_t,
                'is_available': expected_available,
                'reason': f'Test {override_type}',
            })
            self.assertTrue(serializer.is_valid(), f"Failed for {override_type}: {serializer.errors}")
            instance = serializer.save()
            self.assertEqual(instance.override_type, override_type)
            self.assertEqual(instance.is_available, expected_available)

    def test_human_label_mapping(self):
        # Sending human label 'Extended Hours' should map to 'EXTENDED_HOURS'
        today = datetime.date.today()
        serializer = ScheduleOverrideSerializer(data={
            'doctor': self.doctor.id,
            'override_date': str(today + datetime.timedelta(days=5)),
            'override_type': 'Extended Hours',
            'start_time': '08:00:00',
            'end_time': '17:00:00',
            'reason': 'Evening Clinic',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertEqual(instance.override_type, 'EXTENDED_HOURS')
        self.assertEqual(instance.get_override_type_display(), 'Extended Hours')

    def test_closed_type_nullifies_times_and_marks_unavailable(self):
        today = datetime.date.today()
        serializer = ScheduleOverrideSerializer(data={
            'doctor': self.doctor.id,
            'override_date': str(today + datetime.timedelta(days=6)),
            'override_type': 'Closed',
            'start_time': '09:00:00',
            'end_time': '13:00:00',
            'reason': 'Hospital Holiday',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertEqual(instance.override_type, 'CLOSED')
        self.assertFalse(instance.is_available)
        self.assertIsNone(instance.start_time)
        self.assertIsNone(instance.end_time)

    def test_invalid_time_validation(self):
        today = datetime.date.today()
        serializer = ScheduleOverrideSerializer(data={
            'doctor': self.doctor.id,
            'override_date': str(today + datetime.timedelta(days=7)),
            'override_type': 'EXTENDED_HOURS',
            'start_time': '15:00:00',
            'end_time': '11:00:00',
            'reason': 'Should Fail',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_time', serializer.errors)

    def test_api_endpoint_post_and_get(self):
        today = datetime.date.today()
        resp = self.client.post('/api/schedules/overrides/', {
            'doctor': self.doctor.id,
            'override_date': str(today + datetime.timedelta(days=8)),
            'override_type': 'Special OPD',
            'start_time': '08:30:00',
            'end_time': '13:30:00',
            'reason': 'Special API Test',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['override_type'], 'SPECIAL_OPD')
        self.assertEqual(resp.data['override_type_display'], 'Special OPD')

        # Retrieve
        get_resp = self.client.get(f'/api/schedules/overrides/?doctor={self.doctor.id}')
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(get_resp.data.get('results', [])), 1)
