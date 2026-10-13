import logging
import uuid
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from apps.notifications.models import Notification
from apps.appointments.models import Appointment

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Core notification service for Eagle Sora Hospital.
    Handles message composition, delivery state management, idempotency protection,
    and SMTP dispatch.
    """

    HOSPITAL_NAME = "Eagle Sora Hospital"

    @classmethod
    def get_recipient_email(cls, appointment):
        """Resolves recipient email address from appointment patient or user profile."""
        if not appointment or not appointment.patient:
            return None
        patient = appointment.patient
        if patient.user and patient.user.email:
            return patient.user.email
        if hasattr(patient, 'email') and patient.email:
            return patient.email
        return None

    @classmethod
    def compose_confirmation_message(cls, appointment):
        """Generates clean confirmation subject and plain-text body."""
        doctor_name = appointment.doctor.name if appointment.doctor else "Hospital Staff Physician"
        specialty = (
            appointment.doctor.specialty.name
            if appointment.doctor and appointment.doctor.specialty
            else "General Medicine"
        )
        department_name = (
            appointment.department.name
            if appointment.department
            else "Outpatient Department"
        )
        start_str = appointment.start_time.strftime('%H:%M') if appointment.start_time else "Scheduled Time"
        end_str = appointment.end_time.strftime('%H:%M') if appointment.end_time else ""
        time_display = f"{start_str} - {end_str}" if end_str else start_str
        location = appointment.consultation_location or "Main Consultation Wing"

        subject = f"[{cls.HOSPITAL_NAME}] Appointment Confirmed - {appointment.reference}"
        body = (
            f"Dear Patient,\n\n"
            f"Your appointment at {cls.HOSPITAL_NAME} has been successfully confirmed.\n\n"
            f"APPOINTMENT DETAILS:\n"
            f"--------------------------------------------------\n"
            f"Reference:            {appointment.reference}\n"
            f"Doctor:               {doctor_name} ({specialty})\n"
            f"Department:           {department_name}\n"
            f"Date:                 {appointment.appointment_date}\n"
            f"Time:                 {time_display}\n"
            f"Location:             {location}\n"
            f"Type:                 {appointment.get_appointment_type_display()}\n"
            f"Reason for Visit:     {appointment.reason_for_visit or 'General Consultation'}\n"
            f"--------------------------------------------------\n\n"
            f"INSTRUCTIONS:\n"
            f"- Please arrive 15 minutes before your scheduled appointment time.\n"
            f"- Bring any previous medical records, prescriptions, and a valid photo ID.\n"
            f"- If you need to reschedule or cancel, please do so via the patient portal.\n\n"
            f"Thank you for choosing {cls.HOSPITAL_NAME}.\n"
        )
        return subject, body

    @classmethod
    def compose_cancellation_message(cls, appointment, reason=""):
        """Generates cancellation subject and plain-text body."""
        doctor_name = appointment.doctor.name if appointment.doctor else "Hospital Staff Physician"
        start_str = appointment.start_time.strftime('%H:%M') if appointment.start_time else "Scheduled Time"
        cancel_reason = reason or appointment.cancellation_reason or "Cancelled by request"

        subject = f"[{cls.HOSPITAL_NAME}] Appointment Cancelled - {appointment.reference}"
        body = (
            f"Dear Patient,\n\n"
            f"Your appointment at {cls.HOSPITAL_NAME} has been cancelled.\n\n"
            f"CANCELLATION DETAILS:\n"
            f"--------------------------------------------------\n"
            f"Reference:            {appointment.reference}\n"
            f"Doctor:               {doctor_name}\n"
            f"Date:                 {appointment.appointment_date}\n"
            f"Time:                 {start_str}\n"
            f"Reason:               {cancel_reason}\n"
            f"Status:               CANCELLED\n"
            f"--------------------------------------------------\n\n"
            f"If this cancellation was in error or you would like to book a new consultation,\n"
            f"please visit the patient portal or contact our reception desk.\n\n"
            f"{cls.HOSPITAL_NAME}\n"
        )
        return subject, body

    @classmethod
    def compose_reschedule_message(cls, new_appointment, original_appointment=None):
        """Generates rescheduling subject and plain-text body."""
        doctor_name = new_appointment.doctor.name if new_appointment.doctor else "Hospital Staff Physician"
        department_name = (
            new_appointment.department.name
            if new_appointment.department
            else "Outpatient Department"
        )
        start_str = new_appointment.start_time.strftime('%H:%M') if new_appointment.start_time else "Scheduled Time"
        end_str = new_appointment.end_time.strftime('%H:%M') if new_appointment.end_time else ""
        time_display = f"{start_str} - {end_str}" if end_str else start_str
        location = new_appointment.consultation_location or "Main Consultation Wing"

        prev_ref = original_appointment.reference if original_appointment else "Previous Appointment"
        prev_date = original_appointment.appointment_date if original_appointment else "Previous Date"

        subject = f"[{cls.HOSPITAL_NAME}] Appointment Rescheduled - {new_appointment.reference}"
        body = (
            f"Dear Patient,\n\n"
            f"Your appointment at {cls.HOSPITAL_NAME} has been rescheduled.\n\n"
            f"UPDATED APPOINTMENT DETAILS:\n"
            f"--------------------------------------------------\n"
            f"New Reference:        {new_appointment.reference}\n"
            f"Previous Reference:   {prev_ref} (Original Date: {prev_date})\n"
            f"Doctor:               {doctor_name}\n"
            f"Department:           {department_name}\n"
            f"New Date:             {new_appointment.appointment_date}\n"
            f"New Time:             {time_display}\n"
            f"Location:             {location}\n"
            f"Status:               CONFIRMED\n"
            f"--------------------------------------------------\n\n"
            f"Please arrive 15 minutes before your new consultation time.\n\n"
            f"Thank you for choosing {cls.HOSPITAL_NAME}.\n"
        )
        return subject, body

    @classmethod
    def compose_reminder_message(cls, appointment):
        """Generates appointment reminder subject and plain-text body."""
        doctor_name = appointment.doctor.name if appointment.doctor else "Hospital Staff Physician"
        department_name = (
            appointment.department.name
            if appointment.department
            else "Outpatient Department"
        )
        start_str = appointment.start_time.strftime('%H:%M') if appointment.start_time else "Scheduled Time"
        location = appointment.consultation_location or "Main Consultation Wing"

        subject = f"[{cls.HOSPITAL_NAME}] Reminder: Upcoming Appointment Tomorrow - {appointment.reference}"
        body = (
            f"Dear Patient,\n\n"
            f"This is a friendly reminder of your upcoming consultation at {cls.HOSPITAL_NAME} tomorrow.\n\n"
            f"APPOINTMENT DETAILS:\n"
            f"--------------------------------------------------\n"
            f"Reference:            {appointment.reference}\n"
            f"Doctor:               {doctor_name}\n"
            f"Department:           {department_name}\n"
            f"Date:                 {appointment.appointment_date}\n"
            f"Time:                 {start_str}\n"
            f"Location:             {location}\n"
            f"--------------------------------------------------\n\n"
            f"Please arrive 15 minutes prior to your appointment time.\n\n"
            f"{cls.HOSPITAL_NAME}\n"
        )
        return subject, body

    @classmethod
    def compose_staff_alert_message(cls, appointment, event_type="CREATED"):
        """Generates staff alert subject and plain-text body."""
        doctor_name = appointment.doctor.name if appointment.doctor else "Unknown Doctor"
        patient_name = appointment.patient.full_name if appointment.patient else "Unknown Patient"
        start_str = appointment.start_time.strftime('%H:%M') if appointment.start_time else "Scheduled Time"

        subject = f"[{cls.HOSPITAL_NAME} Staff Alert] Appointment {event_type} - {appointment.reference}"
        body = (
            f"Staff Notification Alert:\n\n"
            f"An appointment event has occurred.\n\n"
            f"Event Type:           {event_type}\n"
            f"Reference:            {appointment.reference}\n"
            f"Patient:              {patient_name}\n"
            f"Doctor:               {doctor_name}\n"
            f"Date:                 {appointment.appointment_date}\n"
            f"Time:                 {start_str}\n"
            f"Status:               {appointment.status}\n"
        )
        return subject, body

    @classmethod
    def send_email_notification(cls, notification_id):
        """
        Loads notification by ID, executes SMTP delivery via Django mail backend,
        and atomically updates status and timestamps.
        Idempotent: If already SENT, skips duplicate dispatch.
        """
        notification = Notification.objects.select_related(
            'appointment',
            'appointment__patient',
            'appointment__patient__user',
        ).get(id=notification_id)

        if notification.status == Notification.Status.SENT:
            logger.info(
                f"[NOTIFICATION_IDEMPOTENT_SKIP] Notification {notification_id} is already SENT. Skipping."
            )
            return notification

        recipient_email = notification.recipient
        if not recipient_email:
            notification.status = Notification.Status.FAILED
            notification.failed_at = timezone.now()
            notification.error_message = "No recipient email address available."
            notification.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
            logger.warning(
                f"[NOTIFICATION_NO_RECIPIENT] Notification {notification_id} failed: No recipient email."
            )
            return notification

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hospitalplatform.local')

        try:
            logger.info(
                f"[NOTIFICATION_SENDING] Dispatching notification {notification_id} ({notification.notification_type}) to {recipient_email}."
            )
            send_mail(
                subject=notification.subject,
                message=notification.message,
                from_email=from_email,
                recipient_list=[recipient_email],
                fail_silently=False,
            )

            # Record success
            notification.status = Notification.Status.SENT
            notification.sent_at = timezone.now()
            notification.provider_reference = f"smtp-{uuid.uuid4().hex[:12]}"
            notification.error_message = ""
            notification.save(
                update_fields=[
                    'status',
                    'sent_at',
                    'provider_reference',
                    'error_message',
                    'updated_at',
                ]
            )
            logger.info(
                f"[NOTIFICATION_SENT] Notification {notification_id} successfully sent to {recipient_email}."
            )
            return notification

        except Exception as exc:
            notification.retry_count += 1
            notification.failed_at = timezone.now()
            notification.error_message = str(exc)
            notification.save(
                update_fields=['retry_count', 'failed_at', 'error_message', 'updated_at']
            )
            logger.error(
                f"[NOTIFICATION_FAILED] Dispatch failed for notification {notification_id}: {exc}"
            )
            raise exc


# Safe task trigger utilities (fail-safe wrappers with transaction.on_commit)
def safe_dispatch_confirmation(appointment_id):
    """Queues confirmation email task after database transaction commits."""
    def _enqueue():
        try:
            from apps.notifications.tasks import send_appointment_confirmation_task
            send_appointment_confirmation_task.delay(appointment_id)
            logger.info(f"[TASK_QUEUED] Confirmation task queued for appointment {appointment_id}.")
        except Exception as exc:
            logger.error(
                f"[TASK_QUEUE_FAILED] Failed to queue confirmation task for appointment {appointment_id}: {exc}"
            )

    transaction.on_commit(_enqueue)


def safe_dispatch_cancellation(appointment_id, reason=""):
    """Queues cancellation email task after database transaction commits."""
    def _enqueue():
        try:
            from apps.notifications.tasks import send_appointment_cancellation_task
            send_appointment_cancellation_task.delay(appointment_id, reason)
            logger.info(f"[TASK_QUEUED] Cancellation task queued for appointment {appointment_id}.")
        except Exception as exc:
            logger.error(
                f"[TASK_QUEUE_FAILED] Failed to queue cancellation task for appointment {appointment_id}: {exc}"
            )

    transaction.on_commit(_enqueue)


def safe_dispatch_reschedule(new_appointment_id, original_appointment_id=None):
    """Queues reschedule email task after database transaction commits."""
    def _enqueue():
        try:
            from apps.notifications.tasks import send_appointment_reschedule_task
            send_appointment_reschedule_task.delay(new_appointment_id, original_appointment_id)
            logger.info(f"[TASK_QUEUED] Reschedule task queued for appointment {new_appointment_id}.")
        except Exception as exc:
            logger.error(
                f"[TASK_QUEUE_FAILED] Failed to queue reschedule task for appointment {new_appointment_id}: {exc}"
            )

    transaction.on_commit(_enqueue)
