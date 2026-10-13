import os
import sys
import smtplib
from pathlib import Path
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import TestCase, override_settings
from django.conf import settings
from django.core import mail
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, PatientProfile
from apps.departments.models import Department
from apps.doctors.models import Doctor, Specialty
from apps.scheduling.models import DoctorSchedule
from apps.appointments.models import Appointment
from apps.appointments.services import (
    AppointmentBookingService,
    SlotConflictError,
    SlotValidationError,
)
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.notifications.tasks import (
    send_appointment_confirmation_task,
    send_appointment_cancellation_task,
    send_appointment_reschedule_task,
    send_appointment_reminder_task,
    send_staff_alert_task,
    process_appointment_reminders_task,
)
from celery.app.task import Task
from config.celery import app as celery_app


class CeleryConfigurationTests(TestCase):
    """Verifies Redis, Celery worker, and Celery Beat periodic task configuration."""

    def test_celery_app_initialized(self):
        """Verify Celery application initialized and namespace loaded."""
        self.assertIsNotNone(celery_app)
        self.assertEqual(celery_app.main, 'hospital_platform')

    def test_celery_broker_and_result_backend_settings(self):
        """Verify broker URL, result backend, and Celery Beat scheduler."""
        self.assertTrue(hasattr(settings, 'CELERY_BROKER_URL'))
        self.assertTrue(hasattr(settings, 'CELERY_RESULT_BACKEND'))
        self.assertIn('redis', settings.CELERY_BROKER_URL.lower())
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULER,
            'django_celery_beat.schedulers:DatabaseScheduler'
        )
        self.assertIn('process-appointment-reminders', settings.CELERY_BEAT_SCHEDULE)

    def test_tasks_registered_in_celery_app(self):
        """Verify all Phase 14 notification and reminder tasks are registered."""
        celery_app.loader.import_default_modules()
        registered = celery_app.tasks.keys()
        expected_tasks = [
            'notifications.send_appointment_confirmation',
            'notifications.send_appointment_cancellation',
            'notifications.send_appointment_reschedule',
            'notifications.send_appointment_reminder',
            'notifications.send_staff_alert',
            'reminders.process_appointment_reminders',
        ]
        for task_name in expected_tasks:
            self.assertIn(task_name, registered, f"Task {task_name} not registered in Celery.")


class AsyncNotificationExecutionTests(TestCase):
    """Tests asynchronous notification tasks, email dispatch, retry, and idempotency."""

    def setUp(self):
        self.client = APIClient()

        # Create Patient User & Profile
        self.patient_user = User.objects.create_user(
            email='patient.phase14@example.com',
            password='Password123!',
            first_name='Ananya',
            last_name='Deshmukh',
            role=User.Role.PATIENT,
        )
        self.patient = PatientProfile.objects.create(
            user=self.patient_user,
            mrn='MRN-P14-001',
            date_of_birth=date(1994, 6, 15),
            gender=PatientProfile.Gender.FEMALE,
            phone='+919876543210',
            blood_group=PatientProfile.BloodGroup.A_POS,
        )

        # Create Staff Doctor & Department
        self.dept = Department.objects.create(
            name='Neurology Services',
            specialty='Brain and Spine Care',
        )
        self.specialty = Specialty.objects.create(
            name='Neurophysiology',
        )
        self.doctor_user = User.objects.create_user(
            email='dr.neurology@hospital.local',
            password='Password123!',
            first_name='Sunil',
            last_name='Rao',
            role=User.Role.DOCTOR_STAFF,
        )
        self.doctor = Doctor.objects.create(
            user=self.doctor_user,
            department=self.dept,
            specialty=self.specialty,
            name='Dr. Sunil Rao',
            qualification='MBBS, MD, DM (Neuro)',
            experience_years=16,
            consultation_duration_minutes=30,
            consultation_location='Neuro Outpatient Clinic B',
            is_active=True,
        )

        # Weekly schedule on all days
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for d in days:
            DoctorSchedule.objects.create(
                doctor=self.doctor,
                day_of_week=d,
                start_time=time(9, 0),
                end_time=time(17, 0),
                slot_duration_minutes=30,
                capacity=1,
                is_working_day=True,
                is_active=True,
                timezone='Asia/Kolkata',
            )

        # Clear mail outbox
        mail.outbox.clear()

    def test_confirmation_notification_sent_successfully(self):
        """Verify confirmation task creates Notification record and delivers email."""
        target_date = date.today() + timedelta(days=5)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            reason_for_visit='Chronic migraine consult',
        )

        # Execute confirmation task synchronously (testing task logic directly)
        res = send_appointment_confirmation_task(apt.id)
        self.assertEqual(res.get('status'), 'sent')

        # Check notification record
        notif = Notification.objects.get(
            appointment=apt,
            notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMATION,
        )
        self.assertEqual(notif.status, Notification.Status.SENT)
        self.assertEqual(notif.recipient, self.patient_user.email)
        self.assertIn(apt.reference, notif.subject)
        self.assertIn('Dr. Sunil Rao', notif.message)
        self.assertIsNotNone(notif.sent_at)
        self.assertTrue(notif.provider_reference.startswith('smtp-'))

        # Check mail outbox
        self.assertGreaterEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, [self.patient_user.email])
        self.assertIn(apt.reference, sent_email.subject)
        self.assertIn('Neuro Outpatient Clinic B', sent_email.body)

    def test_confirmation_task_idempotency(self):
        """Verify duplicate delivery of confirmation task does not send multiple emails."""
        target_date = date.today() + timedelta(days=6)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(11, 0),
            end_time=time(11, 30),
        )

        # First dispatch
        res1 = send_appointment_confirmation_task(apt.id)
        self.assertEqual(res1.get('status'), 'sent')
        initial_outbox_len = len(mail.outbox)

        # Second dispatch of identical task
        res2 = send_appointment_confirmation_task(apt.id)
        self.assertEqual(res2.get('status'), 'already_sent')

        # Mail count must NOT increase
        self.assertEqual(len(mail.outbox), initial_outbox_len)
        notifs = Notification.objects.filter(
            appointment=apt,
            notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMATION,
        )
        self.assertEqual(notifs.count(), 1)

    def test_cancellation_notification_sent_successfully(self):
        """Verify cancellation task sends cancellation email with reason."""
        target_date = date.today() + timedelta(days=7)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(14, 0),
            end_time=time(14, 30),
        )

        # Cancel appointment
        AppointmentBookingService.cancel_appointment(
            apt, user=self.patient_user, reason='Patient travel conflict'
        )

        mail.outbox.clear()
        res = send_appointment_cancellation_task(apt.id, reason='Patient travel conflict')
        self.assertEqual(res.get('status'), 'sent')

        notif = Notification.objects.get(
            appointment=apt,
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLATION,
        )
        self.assertEqual(notif.status, Notification.Status.SENT)
        self.assertIn('Cancelled', notif.subject)
        self.assertIn('Patient travel conflict', notif.message)
        self.assertEqual(len(mail.outbox), 1)

    def test_reschedule_notification_sent_successfully(self):
        """Verify rescheduling task sends updated appointment details."""
        target_date = date.today() + timedelta(days=8)
        new_date = date.today() + timedelta(days=9)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(15, 0),
            end_time=time(15, 30),
        )

        new_apt = AppointmentBookingService.reschedule_appointment(
            apt,
            user=self.patient_user,
            new_date=new_date,
            new_start_time=time(10, 0),
            new_end_time=time(10, 30),
            reason='Schedule adjustment',
        )

        mail.outbox.clear()
        res = send_appointment_reschedule_task(new_apt.id, apt.id)
        self.assertEqual(res.get('status'), 'sent')

        notif = Notification.objects.get(
            appointment=new_apt,
            notification_type=Notification.NotificationType.APPOINTMENT_RESCHEDULE,
        )
        self.assertEqual(notif.status, Notification.Status.SENT)
        self.assertIn(new_apt.reference, notif.subject)
        self.assertIn(apt.reference, notif.message)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminder_notification_and_status_filter(self):
        """Verify reminder task sends email for CONFIRMED appointment and skips non-confirmed."""
        target_date = date.today() + timedelta(days=1)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(16, 0),
            end_time=time(16, 30),
            status=Appointment.Status.CONFIRMED,
        )

        mail.outbox.clear()
        res = send_appointment_reminder_task(apt.id)
        self.assertEqual(res.get('status'), 'sent')
        self.assertEqual(len(mail.outbox), 1)

        # Cancel appointment and test reminder is skipped
        apt.status = Appointment.Status.CANCELLED
        apt.save(update_fields=['status'])

        res_skip = send_appointment_reminder_task(apt.id)
        self.assertEqual(res_skip.get('status'), 'skipped')

    def test_beat_process_reminders_task_scans_and_dispatches(self):
        """Verify Celery Beat reminder scanner only targets tomorrow's confirmed appointments."""
        tz = ZoneInfo("Asia/Kolkata")
        tomorrow = timezone.now().astimezone(tz).date() + timedelta(days=1)
        five_days_later = tomorrow + timedelta(days=4)

        # Apt 1: Eligible tomorrow
        apt_tomorrow, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=tomorrow,
            start_time=time(9, 30),
            end_time=time(10, 0),
            status=Appointment.Status.CONFIRMED,
        )

        # Apt 2: Future, not tomorrow
        apt_future, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=five_days_later,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.CONFIRMED,
        )

        with patch('apps.notifications.tasks.send_appointment_reminder_task.delay') as mock_delay:
            summary = process_appointment_reminders_task()
            self.assertGreaterEqual(summary['processed'], 1)
            mock_delay.assert_called_with(apt_tomorrow.id)

    def test_retry_on_temporary_smtp_failure(self):
        """Verify temporary email failure triggers task retry with exponential backoff."""
        target_date = date.today() + timedelta(days=10)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(12, 0),
            end_time=time(12, 30),
        )

        with patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPException("Connection timed out")):
            with patch.object(Task, 'retry', side_effect=Exception("CeleryRetry")) as mock_retry:
                try:
                    send_appointment_confirmation_task.apply(args=[apt.id], retries=0)
                except Exception as e:
                    self.assertEqual(str(e), "CeleryRetry")
                mock_retry.assert_called_once()
                kwargs = mock_retry.call_args.kwargs
                self.assertIn('countdown', kwargs)
                self.assertEqual(kwargs['countdown'], 5)  # 5 * (2**0) = 5s

    def test_max_retries_exceeded_records_permanent_failure(self):
        """Verify task records Status.FAILED when max retries are exhausted."""
        target_date = date.today() + timedelta(days=11)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(12, 30),
            end_time=time(13, 0),
        )

        with patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPException("Permanent refusal")):
            res = send_appointment_confirmation_task.apply(args=[apt.id], retries=3)
            result = res.get()
            self.assertEqual(result.get('status'), 'failed')

            notif = Notification.objects.get(
                appointment=apt,
                notification_type=Notification.NotificationType.APPOINTMENT_CONFIRMATION,
            )
            self.assertEqual(notif.status, Notification.Status.FAILED)
            self.assertIn("Max retries", notif.error_message)
            self.assertIsNotNone(notif.failed_at)

    def test_failure_isolation_smtp_failure_does_not_break_booking(self):
        """Verify appointment booking succeeds even if notification delivery fails."""
        target_date = date.today() + timedelta(days=12)

        # Mock send_mail to raise SMTPException
        with patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPException("SMTP Server Unreachable")):
            self.client.force_authenticate(user=self.patient_user)
            payload = {
                "doctor": self.doctor.id,
                "appointment_date": str(target_date),
                "start_time": "14:00:00",
                "end_time": "14:30:00",
                "appointment_type": "IN_PERSON",
                "reason_for_visit": "Headache consultation",
            }
            response = self.client.post('/api/appointments/', payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.json()
            self.assertEqual(data.get('status'), 'REQUESTED')
            self.assertTrue(Appointment.objects.filter(reference=data.get('reference')).exists())

    def test_failure_isolation_redis_failure_does_not_break_booking_api(self):
        """Verify API returns HTTP 201 Created even if Redis / Celery broker is unavailable."""
        target_date = date.today() + timedelta(days=13)

        with patch(
            'apps.notifications.tasks.send_appointment_confirmation_task.delay',
            side_effect=Exception("Redis Connection Refused on 6379"),
        ):
            self.client.force_authenticate(user=self.patient_user)
            payload = {
                "doctor": self.doctor.id,
                "appointment_date": str(target_date),
                "start_time": "15:00:00",
                "end_time": "15:30:00",
                "appointment_type": "IN_PERSON",
                "reason_for_visit": "Routine checkup",
            }
            response = self.client.post('/api/appointments/', payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_failure_isolation_smtp_failure_does_not_break_cancellation(self):
        """Verify appointment cancellation succeeds even if cancellation email fails."""
        target_date = date.today() + timedelta(days=14)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(16, 0),
            end_time=time(16, 30),
        )

        with patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPException("SMTP down")):
            self.client.force_authenticate(user=self.patient_user)
            response = self.client.post(
                f'/api/appointments/{apt.reference}/cancel/',
                {'reason': 'Cancellation test with SMTP down'},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            apt.refresh_from_db()
            self.assertEqual(apt.status, Appointment.Status.CANCELLED)

    def test_failure_isolation_smtp_failure_does_not_break_rescheduling(self):
        """Verify appointment rescheduling succeeds even if rescheduling email fails."""
        target_date = date.today() + timedelta(days=15)
        new_date = date.today() + timedelta(days=16)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.CONFIRMED,
        )

        with patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPException("SMTP down")):
            self.client.force_authenticate(user=self.patient_user)
            payload = {
                'appointment_date': str(new_date),
                'start_time': '11:00:00',
                'end_time': '11:30:00',
                'reason': 'Reschedule test with SMTP down',
            }
            response = self.client.post(
                f'/api/appointments/{apt.reference}/reschedule/',
                payload,
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            new_ref = response.json().get('reference')
            self.assertTrue(Appointment.objects.filter(reference=new_ref, status=Appointment.Status.CONFIRMED).exists())

    def test_transaction_rollback_does_not_dispatch_notification(self):
        """Verify that when an appointment booking transaction rolls back, no task is queued."""
        target_date = date.today() + timedelta(days=17)

        # Pre-book slot to cause conflict
        AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )

        with patch('apps.notifications.tasks.send_appointment_confirmation_task.delay') as mock_delay:
            # Second booking will conflict and rollback
            with self.assertRaises(SlotConflictError):
                AppointmentBookingService.book_appointment(
                    patient=self.patient,
                    doctor=self.doctor,
                    appointment_date=target_date,
                    start_time=time(10, 0),
                    end_time=time(10, 30),
                )
            mock_delay.assert_not_called()

    def test_staff_alert_task_records_audit_notification(self):
        """Verify send_staff_alert_task creates an ADMIN_ALERT notification record."""
        target_date = date.today() + timedelta(days=18)
        apt, _ = AppointmentBookingService.book_appointment(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=target_date,
            start_time=time(11, 30),
            end_time=time(12, 0),
        )

        res = send_staff_alert_task(apt.id, "TEST_EVENT")
        self.assertEqual(res.get('status'), 'recorded')

        notif = Notification.objects.get(
            appointment=apt,
            notification_type=Notification.NotificationType.ADMIN_ALERT,
        )
        self.assertEqual(notif.channel, Notification.Channel.SYSTEM)
        self.assertIn("Staff Alert", notif.subject)


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_celery_notifications'])
    sys.exit(bool(failures))

