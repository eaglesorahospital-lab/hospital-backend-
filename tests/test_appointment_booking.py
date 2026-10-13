import os
import sys
from pathlib import Path
import concurrent.futures
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import TransactionTestCase
from django.utils import timezone
from django.db import connection
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User, PatientProfile
from apps.departments.models import Department
from apps.doctors.models import Doctor, Specialty
from apps.scheduling.models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
from apps.appointments.models import Appointment
from apps.appointments.services import (
    AppointmentBookingService,
    SlotConflictError,
    SlotValidationError,
    AppointmentStateError,
)
from apps.scheduling.services import AvailabilityEngine


class AppointmentBookingComprehensiveTests(TransactionTestCase):
    """
    Phase 13 Comprehensive Test Suite:
    - Authoritative Availability Engine & deterministic slot generation
    - Transactional booking with PostgreSQL row-locking (select_for_update)
    - Double-booking prevention and true concurrency testing
    - Rescheduling & atomic rollback protection
    - Cancellation & lifecycle transitions
    - Idempotency protection with database uniqueness
    - Role-based and object-level authorization
    """

    def setUp(self):
        # 1. Department & Specialty
        self.dept = Department.objects.create(
            name="Cardiology",
            slug="cardiology",
            specialty="Cardiovascular Sciences",
            is_active=True,
        )
        self.specialty = Specialty.objects.create(
            name="Cardiology Specialty",
            slug="cardiology-specialty",
            is_active=True,
        )

        # 2. Doctors
        self.doctor = Doctor.objects.create(
            name="Dr. Sarah Jenkins",
            slug="dr-sarah-jenkins",
            department=self.dept,
            specialty=self.specialty,
            qualification="MD, DM (Cardiology)",
            consultation_duration_minutes=30,
            consultation_location="Wing A, Suite 101",
            is_active=True,
        )
        self.inactive_doctor = Doctor.objects.create(
            name="Dr. Inactive Physician",
            slug="dr-inactive-physician",
            department=self.dept,
            specialty=self.specialty,
            qualification="MBBS",
            is_active=False,
        )

        # 3. Weekly Schedules for all days for Dr. Sarah Jenkins (09:00 - 13:00)
        for day in DoctorSchedule.DayOfWeek.values:
            DoctorSchedule.objects.create(
                doctor=self.doctor,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(13, 0),
                slot_duration_minutes=30,
                capacity=1,
                timezone="Asia/Kolkata",
                is_working_day=True,
                is_active=True,
            )

        # Add a lunch break on all schedules between 12:00 and 12:30
        for sched in DoctorSchedule.objects.filter(doctor=self.doctor):
            ScheduleBreak.objects.create(
                schedule=sched,
                name="Clinical Recess",
                start_time=time(12, 0),
                end_time=time(12, 30),
            )

        # 4. Users & Profiles
        self.patient_user_a = User.objects.create_user(
            email="patient.a@example.com",
            password="SecurePassword123!",
            first_name="Alice",
            last_name="Smith",
            role=User.Role.PATIENT,
        )
        self.patient_a = PatientProfile.objects.create(
            user=self.patient_user_a,
            mrn="MRN-ALICE-01",
            first_name="Alice",
            last_name="Smith",
            is_active=True,
        )

        self.patient_user_b = User.objects.create_user(
            email="patient.b@example.com",
            password="SecurePassword123!",
            first_name="Bob",
            last_name="Jones",
            role=User.Role.PATIENT,
        )
        self.patient_a_inactive = PatientProfile.objects.create(
            user=None,
            mrn="MRN-INACTIVE-01",
            first_name="Inactive",
            last_name="Patient",
            is_active=False,
        )
        self.patient_b = PatientProfile.objects.create(
            user=self.patient_user_b,
            mrn="MRN-BOB-02",
            first_name="Bob",
            last_name="Jones",
            is_active=True,
        )

        self.admin_user = User.objects.create_user(
            email="admin.booking@example.com",
            password="AdminPassword123!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        # 5. API Clients
        self.client_a = APIClient()
        self.token_a = str(RefreshToken.for_user(self.patient_user_a).access_token)
        self.client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")

        self.client_b = APIClient()
        self.token_b = str(RefreshToken.for_user(self.patient_user_b).access_token)
        self.client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_b}")

        self.admin_client = APIClient()
        self.token_admin = str(RefreshToken.for_user(self.admin_user).access_token)
        self.admin_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_admin}")

        self.anon_client = APIClient()

        # Future booking target date: 7 days from now
        self.future_date = date.today() + timedelta(days=7)

    # 1. Valid booking succeeds
    def test_01_valid_booking_succeeds(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
            "appointment_type": "IN_PERSON",
            "reason_for_visit": "Annual cardiology checkup.",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertTrue(data['reference'].startswith('APT-'))
        self.assertEqual(data['status'], 'REQUESTED')
        self.assertEqual(data['patient']['mrn'], self.patient_a.mrn)
        self.assertEqual(data['doctor']['id'], self.doctor.id)
        self.assertEqual(data['department']['id'], self.dept.id)

    # 2. Booking requires authentication
    def test_02_booking_requires_authentication(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.anon_client.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # 3. Patient cannot book for another patient
    def test_03_patient_cannot_book_for_another_patient(self):
        payload = {
            "doctor": self.doctor.id,
            "patient": self.patient_b.id,  # Patient A attempts to book using Patient B's profile ID
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        # Must be bound to Patient A regardless of the payload's patient field
        self.assertEqual(data['patient']['mrn'], self.patient_a.mrn)
        self.assertNotEqual(data['patient']['id'], self.patient_b.id)

    # 4. Invalid doctor rejected
    def test_04_invalid_doctor_rejected(self):
        payload = {
            "doctor": 99999,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # 5. Inactive doctor rejected
    def test_05_inactive_doctor_rejected(self):
        payload = {
            "doctor": self.inactive_doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # 6. Invalid date format rejected
    def test_06_invalid_date_rejected(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": "invalid-date",
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # 7. Past slot rejected
    def test_07_past_slot_rejected(self):
        past_date = date.today() - timedelta(days=2)
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(past_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # 8. Non-working day rejected
    def test_08_non_working_day_rejected(self):
        # Set Sunday as non-working day
        DoctorSchedule.objects.filter(
            doctor=self.doctor, day_of_week=DoctorSchedule.DayOfWeek.SUNDAY
        ).update(is_working_day=False)

        # Find next Sunday
        days_until_sunday = (6 - self.future_date.weekday()) % 7
        next_sunday = self.future_date + timedelta(days=days_until_sunday)

        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(next_sunday),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # 9. Doctor leave blocks booking
    def test_09_doctor_leave_blocks_booking(self):
        DoctorLeave.objects.create(
            doctor=self.doctor,
            start_date=self.future_date - timedelta(days=1),
            end_date=self.future_date + timedelta(days=1),
            reason="Cardiology Conference",
            is_active=True,
        )
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("leave", res.json()['detail'].lower())

    # 10. Break blocks booking
    def test_10_break_blocks_booking(self):
        # Recess is 12:00 to 12:30
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "12:00:00",
            "end_time": "12:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("break", res.json()['detail'].lower())

    # 11. Override blocks booking
    def test_11_override_blocks_booking(self):
        ScheduleOverride.objects.create(
            doctor=self.doctor,
            override_date=self.future_date,
            is_available=False,
            reason="Hospital Renovation",
        )
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("unavailable", res.json()['detail'].lower())

    # 12. Slot outside working hours rejected
    def test_12_slot_outside_working_hours_rejected(self):
        # Shift is 09:00 - 13:00. Request 15:00 - 15:30.
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "15:00:00",
            "end_time": "15:30:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outside doctor shift hours", res.json()['detail'])

    # 13. Invalid slot duration rejected
    def test_13_invalid_slot_duration_rejected(self):
        # Schedule requires 30 mins. Request 45 mins.
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:45:00",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slot duration", res.json()['detail'].lower())

    # 14. Already booked slot rejected
    def test_14_already_booked_slot_rejected(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        # First booking succeeds
        res1 = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second booking fails with 409
        res2 = self.client_b.post('/api/appointments/', payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("no longer available", res2.json()['detail'])

    # 15. Capacity respected
    def test_15_capacity_respected(self):
        # Configure capacity = 2 on Friday
        DoctorSchedule.objects.filter(doctor=self.doctor).update(capacity=2)

        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "09:30:00",
            "end_time": "10:00:00",
        }
        # 1st booking succeeds
        res1 = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # 2nd booking succeeds because capacity is 2
        res2 = self.client_b.post('/api/appointments/', payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # 3rd booking fails with 409
        res3 = self.admin_client.post(
            '/api/appointments/',
            {**payload, "patient": self.patient_a.id},
            format='json',
        )
        self.assertEqual(res3.status_code, status.HTTP_409_CONFLICT)

    # 16. Cancellation succeeds and slot is released
    def test_16_cancellation_succeeds(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res_book = self.client_a.post('/api/appointments/', payload, format='json')
        ref = res_book.json()['reference']

        # Cancel
        res_cancel = self.client_a.post(
            f'/api/appointments/{ref}/cancel/',
            {"reason": "Personal conflict"},
            format='json',
        )
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.json()['status'], 'CANCELLED')
        self.assertIsNotNone(res_cancel.json()['cancelled_at'])

        # Now Patient B can book the exact same slot!
        res_rebook = self.client_b.post('/api/appointments/', payload, format='json')
        self.assertEqual(res_rebook.status_code, status.HTTP_201_CREATED)

    # 17. Invalid cancellation rejected
    def test_17_invalid_cancellation_rejected(self):
        apt = Appointment.objects.create(
            patient=self.patient_a,
            doctor=self.doctor,
            department=self.dept,
            appointment_date=self.future_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.COMPLETED,
        )
        res = self.client_a.post(
            f'/api/appointments/{apt.reference}/cancel/',
            {"reason": "Cancel completed"},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be cancelled", res.json()['detail'])

    # 18. Rescheduling succeeds
    def test_18_rescheduling_succeeds(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
        }
        res_book = self.client_a.post('/api/appointments/', payload, format='json')
        orig_ref = res_book.json()['reference']

        # Reschedule to 11:00 - 11:30
        reschedule_payload = {
            "appointment_date": str(self.future_date),
            "start_time": "11:00:00",
            "end_time": "11:30:00",
            "reason": "Rescheduled to late morning slot.",
        }
        res_resched = self.client_a.post(
            f'/api/appointments/{orig_ref}/reschedule/',
            reschedule_payload,
            format='json',
        )
        self.assertEqual(res_resched.status_code, status.HTTP_200_OK)
        new_data = res_resched.json()
        self.assertNotEqual(new_data['reference'], orig_ref)
        self.assertEqual(new_data['start_time'], '11:00:00')
        # Original appointment is RESCHEDULED
        orig_apt = Appointment.objects.get(reference=orig_ref)
        self.assertEqual(new_data['rescheduled_from'], orig_apt.id)
        self.assertEqual(orig_apt.status, Appointment.Status.RESCHEDULED)

        # Original slot (10:00) is now free for Patient B
        res_book_old_slot = self.client_b.post('/api/appointments/', payload, format='json')
        self.assertEqual(res_book_old_slot.status_code, status.HTTP_201_CREATED)

    # 19. Rescheduling to unavailable slot fails
    def test_19_rescheduling_to_unavailable_slot_fails(self):
        # Patient A books 10:00
        res_a = self.client_a.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "10:00:00",
                "end_time": "10:30:00",
            },
            format='json',
        )
        ref_a = res_a.json()['reference']

        # Patient B books 11:00
        self.client_b.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "11:00:00",
                "end_time": "11:30:00",
            },
            format='json',
        )

        # Patient A attempts to reschedule to 11:00 (which Bob has booked)
        res_fail = self.client_a.post(
            f'/api/appointments/{ref_a}/reschedule/',
            {
                "appointment_date": str(self.future_date),
                "start_time": "11:00:00",
                "end_time": "11:30:00",
            },
            format='json',
        )
        self.assertEqual(res_fail.status_code, status.HTTP_409_CONFLICT)

    # 20. Failed reschedule leaves original appointment unchanged
    def test_20_failed_reschedule_leaves_original_appointment_unchanged(self):
        res_a = self.client_a.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "10:00:00",
                "end_time": "10:30:00",
            },
            format='json',
        )
        ref_a = res_a.json()['reference']

        # Attempt reschedule to invalid break slot (12:00)
        res_fail = self.client_a.post(
            f'/api/appointments/{ref_a}/reschedule/',
            {
                "appointment_date": str(self.future_date),
                "start_time": "12:00:00",
                "end_time": "12:30:00",
            },
            format='json',
        )
        self.assertEqual(res_fail.status_code, status.HTTP_409_CONFLICT)

        # Original appointment remains REQUESTED and untouched
        orig_apt = Appointment.objects.get(reference=ref_a)
        self.assertEqual(orig_apt.status, Appointment.Status.REQUESTED)
        self.assertEqual(orig_apt.start_time, time(10, 0))

    # 21. Appointment lifecycle transitions validated
    def test_21_appointment_lifecycle_transitions_validated(self):
        apt = Appointment.objects.create(
            patient=self.patient_a,
            doctor=self.doctor,
            department=self.dept,
            appointment_date=self.future_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.CONFIRMED,
        )
        # CONFIRMED -> CHECKED_IN
        res1 = self.admin_client.patch(
            f'/api/appointments/{apt.reference}/',
            {"status": "CHECKED_IN"},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # CHECKED_IN -> COMPLETED
        res2 = self.admin_client.patch(
            f'/api/appointments/{apt.reference}/',
            {"status": "COMPLETED"},
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # COMPLETED -> CONFIRMED (Disallowed)
        res3 = self.admin_client.patch(
            f'/api/appointments/{apt.reference}/',
            {"status": "CONFIRMED"},
            format='json',
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid appointment status transition", res3.json()['status'][0])

    # 22 & 23. Concurrent booking test & Double-booking prevention
    def test_22_concurrent_booking_test(self):
        """
        True concurrency test using multiple threads against PostgreSQL.
        Both threads attempt to book the exact same slot simultaneously.
        Exactly one MUST succeed (HTTP 201), and the other MUST fail (HTTP 409).
        """
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "10:30:00",
            "end_time": "11:00:00",
            "appointment_type": "IN_PERSON",
        }

        results = []

        def attempt_booking(user, token):
            # Clean connection for independent thread
            connection.close()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post('/api/appointments/', payload, format='json')
            connection.close()
            return response.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(attempt_booking, self.patient_user_a, self.token_a)
            future2 = executor.submit(attempt_booking, self.patient_user_b, self.token_b)

            results.append(future1.result())
            results.append(future2.result())

        # Assert exactly one 201 and one 409
        self.assertIn(status.HTTP_201_CREATED, results)
        self.assertIn(status.HTTP_409_CONFLICT, results)

        # Database verification: exactly one appointment exists for this slot
        count = Appointment.objects.filter(
            doctor=self.doctor,
            appointment_date=self.future_date,
            start_time=time(10, 30),
            end_time=time(11, 0),
        ).exclude(status=Appointment.Status.CANCELLED).count()

        self.assertEqual(count, 1)

    # 24. Transaction rollback test
    def test_24_transaction_rollback_test(self):
        """Verify that an atomic transaction rolls back without creating partial data on error."""
        initial_count = Appointment.objects.count()
        try:
            # Pass invalid duration (45 mins) to trigger exception inside booking service
            AppointmentBookingService.book_appointment(
                patient=self.patient_a,
                doctor=self.doctor,
                appointment_date=self.future_date,
                start_time=time(10, 0),
                end_time=time(10, 45),
            )
        except SlotValidationError:
            pass

        self.assertEqual(Appointment.objects.count(), initial_count)

    # 25. Idempotency test
    def test_25_idempotency_test(self):
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(self.future_date),
            "start_time": "11:00:00",
            "end_time": "11:30:00",
        }
        idempotency_key = "idemp-client-test-uuid-999"

        # First request
        res1 = self.client_a.post(
            '/api/appointments/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        ref1 = res1.json()['reference']

        # Duplicate identical request with same Idempotency-Key
        res2 = self.client_a.post(
            '/api/appointments/',
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key,
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        ref2 = res2.json()['reference']

        # Returns identical appointment reference
        self.assertEqual(ref1, ref2)
        # Database has exactly 1 appointment
        self.assertEqual(Appointment.objects.filter(idempotency_key=idempotency_key).count(), 1)

    # 26. PostgreSQL constraint verification
    def test_26_postgresql_constraint_and_concurrency_verification(self):
        # Database constraint: end_time must be after start_time
        with self.assertRaises(Exception):
            Appointment.objects.create(
                patient=self.patient_a,
                doctor=self.doctor,
                department=self.dept,
                appointment_date=self.future_date,
                start_time=time(11, 0),
                end_time=time(10, 0),
            )

    # 27. Appointment reference remains unique
    def test_27_appointment_reference_remains_unique(self):
        res1 = self.client_a.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "09:00:00",
                "end_time": "09:30:00",
            },
            format='json',
        )
        res2 = self.client_b.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "09:30:00",
                "end_time": "10:00:00",
            },
            format='json',
        )
        self.assertNotEqual(res1.json()['reference'], res2.json()['reference'])

    # 28. Unauthorized appointment access rejected
    def test_28_unauthorized_appointment_access_rejected(self):
        # Patient A creates appointment
        res1 = self.client_a.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "09:00:00",
                "end_time": "09:30:00",
            },
            format='json',
        )
        ref_a = res1.json()['reference']

        # Patient B cannot retrieve Patient A's appointment (404 isolation)
        res_b_view = self.client_b.get(f'/api/appointments/{ref_a}/')
        self.assertEqual(res_b_view.status_code, status.HTTP_404_NOT_FOUND)

        # Patient B cannot cancel Patient A's appointment
        res_b_cancel = self.client_b.post(f'/api/appointments/{ref_a}/cancel/', {"reason": "Malicious cancel"}, format='json')
        self.assertEqual(res_b_cancel.status_code, status.HTTP_404_NOT_FOUND)

    # 29. Doctor/staff access remains scoped
    def test_29_doctor_staff_access_remains_scoped(self):
        # Create doctor staff user
        staff_user = User.objects.create_user(
            email="dr.jenkins@hospital.local",
            password="StaffPassword123!",
            role=User.Role.DOCTOR_STAFF,
        )
        self.doctor.user = staff_user
        self.doctor.save()

        staff_client = APIClient()
        staff_token = str(RefreshToken.for_user(staff_user).access_token)
        staff_client.credentials(HTTP_AUTHORIZATION=f"Bearer {staff_token}")

        # Patient A books with Dr. Jenkins
        res_book = self.client_a.post(
            '/api/appointments/',
            {
                "doctor": self.doctor.id,
                "appointment_date": str(self.future_date),
                "start_time": "09:00:00",
                "end_time": "09:30:00",
            },
            format='json',
        )
        ref = res_book.json()['reference']

        # Staff can view the consultation
        res_staff = staff_client.get(f'/api/appointments/{ref}/')
        self.assertEqual(res_staff.status_code, status.HTTP_200_OK)

    # 30. Admin access works correctly
    def test_30_admin_access_works_correctly(self):
        # Admin can view all appointments platform-wide
        res_admin = self.admin_client.get('/api/appointments/')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    # 31. Availability Endpoint Returns Accurate Slots
    def test_31_doctor_availability_endpoint(self):
        # Check availability on future date
        res = self.anon_client.get(
            f'/api/doctors/{self.doctor.slug}/availability/?date={self.future_date}'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['doctor']['slug'], self.doctor.slug)
        self.assertEqual(data['slot_duration_minutes'], 30)

        slots = data['available_slots']
        # Recess is 12:00 to 12:30 -> should be available=False
        lunch_slot = next((s for s in slots if s['start_time'] == '12:00:00'), None)
        self.assertIsNotNone(lunch_slot)
        self.assertFalse(lunch_slot['available'])

        # Morning slot 10:00 should be available=True
        morning_slot = next((s for s in slots if s['start_time'] == '10:00:00'), None)
        self.assertIsNotNone(morning_slot)
        self.assertTrue(morning_slot['available'])

    # 32. A newly submitted appointment gets REQUESTED
    def test_32_newly_submitted_appointment_defaults_to_requested(self):
        target_date = self.future_date + timedelta(days=2)
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(target_date),
            "start_time": "11:00:00",
            "end_time": "11:30:00",
            "appointment_type": "IN_PERSON",
            "reason_for_visit": "Consultation checkup",
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['status'], 'REQUESTED')

        # Verify database record
        apt = Appointment.objects.get(reference=data['reference'])
        self.assertEqual(apt.status, Appointment.Status.REQUESTED)

    # 33. Patient cannot force CONFIRMED status in booking payload
    def test_33_patient_cannot_force_confirmed_status_in_booking_payload(self):
        target_date = self.future_date + timedelta(days=3)
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(target_date),
            "start_time": "11:00:00",
            "end_time": "11:30:00",
            "appointment_type": "IN_PERSON",
            "reason_for_visit": "Consultation checkup",
            "status": "CONFIRMED",  # Malicious attempt to force CONFIRMED status
        }
        res = self.client_a.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['status'], 'REQUESTED')

        # Verify database record remains REQUESTED
        apt = Appointment.objects.get(reference=data['reference'])
        self.assertEqual(apt.status, Appointment.Status.REQUESTED)

    # 34. Public booking API enforces REQUESTED status
    def test_34_public_booking_api_enforces_requested_status(self):
        target_date = self.future_date + timedelta(days=4)
        payload = {
            "doctor": self.doctor.id,
            "appointment_date": str(target_date),
            "start_time": "10:00:00",
            "end_time": "10:30:00",
            "status": "CONFIRMED",  # Client-supplied status must be ignored
            "patient": {
                "fullName": "Public Test Patient",
                "phone": "+919876543210",
                "email": "public.patient@example.com",
                "gender": "FEMALE",
                "dob": "1995-05-15",
                "reasonForVisit": "Public booking test",
            },
        }
        res = self.anon_client.post('/api/appointments/book/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['status'], 'REQUESTED')

        # Verify database record is saved as REQUESTED
        apt = Appointment.objects.get(reference=data['reference'])
        self.assertEqual(apt.status, Appointment.Status.REQUESTED)

    # 35. Authorized admin can approve requested appointment
    def test_35_authorized_admin_can_approve_requested_appointment(self):
        target_date = self.future_date + timedelta(days=5)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient_a,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.REQUESTED,
        )
        self.assertEqual(apt.status, Appointment.Status.REQUESTED)

        # Admin approves via dedicated approve endpoint
        res = self.admin_client.post(f'/api/appointments/{apt.reference}/approve/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], 'CONFIRMED')

        apt.refresh_from_db()
        self.assertEqual(apt.status, Appointment.Status.CONFIRMED)

        # Admin can also approve via PATCH status
        apt2, _ = AppointmentBookingService.book_appointment(
            patient=self.patient_b,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(11, 0),
            end_time=time(11, 30),
            status=Appointment.Status.REQUESTED,
        )
        res_patch = self.admin_client.patch(
            f'/api/appointments/{apt2.reference}/',
            {"status": "CONFIRMED"},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.json()['status'], 'CONFIRMED')
        apt2.refresh_from_db()
        self.assertEqual(apt2.status, Appointment.Status.CONFIRMED)

    # 36. Unauthorized user cannot approve an appointment
    def test_36_unauthorized_user_cannot_approve_appointment(self):
        target_date = self.future_date + timedelta(days=6)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient_a,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.REQUESTED,
        )

        # Patient attempts to approve via dedicated approve endpoint -> 403 Forbidden
        res_patient_approve = self.client_a.post(f'/api/appointments/{apt.reference}/approve/')
        self.assertEqual(res_patient_approve.status_code, status.HTTP_403_FORBIDDEN)

        # Patient attempts to force CONFIRMED status via PATCH -> 403 Forbidden
        res_patient_patch = self.client_a.patch(
            f'/api/appointments/{apt.reference}/',
            {"status": "CONFIRMED"},
            format='json',
        )
        self.assertEqual(res_patient_patch.status_code, status.HTTP_403_FORBIDDEN)

        # Anonymous user attempts approve -> 401 Unauthorized
        res_anon = self.anon_client.post(f'/api/appointments/{apt.reference}/approve/')
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # In DB, appointment remains REQUESTED
        apt.refresh_from_db()
        self.assertEqual(apt.status, Appointment.Status.REQUESTED)


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_appointment_booking'])
    sys.exit(bool(failures))
