import logging
from zoneinfo import ZoneInfo
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.appointments.models import Appointment

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, name='notifications.send_appointment_confirmation')
def send_appointment_confirmation_task(self, appointment_id):
    """
    Asynchronous Celery task to dispatch an appointment confirmation notification.
    Features:
    - Idempotency protection with PostgreSQL idempotency key
    - Safe delivery recording
    - Exponential backoff retry up to 3 attempts
    - Failure isolation (does not impact booking transaction)
    """
    logger.info(f"[TASK_START] Confirmation task started for appointment {appointment_id}.")
    try:
        appointment = Appointment.objects.select_related(
            'patient',
            'patient__user',
            'doctor',
            'doctor__specialty',
            'department',
        ).get(id=appointment_id)
    except Appointment.DoesNotExist:
        logger.error(f"[TASK_ERROR] Appointment {appointment_id} does not exist.")
        return {"status": "error", "message": "Appointment not found"}

    recipient_email = NotificationService.get_recipient_email(appointment)
    if not recipient_email:
        logger.warning(f"[TASK_WARNING] No recipient email for appointment {appointment.reference}.")
        return {"status": "skipped", "message": "No recipient email"}

    subject, body = NotificationService.compose_confirmation_message(appointment)
    idempotency_key = f"CONFIRM_{appointment.id}"

    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'recipient': recipient_email,
            'recipient_user': appointment.patient.user if appointment.patient else None,
            'appointment': appointment,
            'notification_type': Notification.NotificationType.APPOINTMENT_CONFIRMATION,
            'channel': Notification.Channel.EMAIL,
            'status': Notification.Status.PENDING,
            'subject': subject,
            'message': body,
        },
    )

    # Idempotent skip if already successfully sent
    if not created and notification.status == Notification.Status.SENT:
        logger.info(f"[TASK_ALREADY_SENT] Confirmation notification {notification.id} already SENT.")
        return {"status": "already_sent", "notification_id": notification.id}

    try:
        NotificationService.send_email_notification(notification.id)
        # Asynchronously dispatch staff alert
        try:
            send_staff_alert_task.delay(appointment.id, "CONFIRMED")
        except Exception as staff_alert_err:
            logger.warning(f"[STAFF_ALERT_FAILED] Failed to queue staff alert: {staff_alert_err}")

        return {"status": "sent", "notification_id": notification.id}

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            notification.status = Notification.Status.FAILED
            notification.failed_at = timezone.now()
            notification.error_message = f"Max retries ({self.max_retries}) exceeded: {exc}"
            notification.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
            logger.error(
                f"[TASK_PERMANENT_FAILURE] Confirmation notification {notification.id} permanently failed: {exc}"
            )
            return {"status": "failed", "notification_id": notification.id, "error": str(exc)}

        countdown = 5 * (2 ** self.request.retries)
        logger.warning(
            f"[TASK_RETRY] Retrying confirmation task in {countdown}s (retry {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=3, name='notifications.send_appointment_cancellation')
def send_appointment_cancellation_task(self, appointment_id, reason=""):
    """
    Asynchronous Celery task to dispatch an appointment cancellation notification.
    """
    logger.info(f"[TASK_START] Cancellation task started for appointment {appointment_id}.")
    try:
        appointment = Appointment.objects.select_related(
            'patient',
            'patient__user',
            'doctor',
            'department',
        ).get(id=appointment_id)
    except Appointment.DoesNotExist:
        logger.error(f"[TASK_ERROR] Appointment {appointment_id} does not exist.")
        return {"status": "error", "message": "Appointment not found"}

    recipient_email = NotificationService.get_recipient_email(appointment)
    if not recipient_email:
        logger.warning(f"[TASK_WARNING] No recipient email for appointment {appointment.reference}.")
        return {"status": "skipped", "message": "No recipient email"}

    subject, body = NotificationService.compose_cancellation_message(appointment, reason=reason)
    idempotency_key = f"CANCEL_{appointment.id}"

    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'recipient': recipient_email,
            'recipient_user': appointment.patient.user if appointment.patient else None,
            'appointment': appointment,
            'notification_type': Notification.NotificationType.APPOINTMENT_CANCELLATION,
            'channel': Notification.Channel.EMAIL,
            'status': Notification.Status.PENDING,
            'subject': subject,
            'message': body,
        },
    )

    if not created and notification.status == Notification.Status.SENT:
        logger.info(f"[TASK_ALREADY_SENT] Cancellation notification {notification.id} already SENT.")
        return {"status": "already_sent", "notification_id": notification.id}

    try:
        NotificationService.send_email_notification(notification.id)
        try:
            send_staff_alert_task.delay(appointment.id, "CANCELLED")
        except Exception as staff_alert_err:
            logger.warning(f"[STAFF_ALERT_FAILED] Failed to queue staff alert: {staff_alert_err}")

        return {"status": "sent", "notification_id": notification.id}

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            notification.status = Notification.Status.FAILED
            notification.failed_at = timezone.now()
            notification.error_message = f"Max retries ({self.max_retries}) exceeded: {exc}"
            notification.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
            logger.error(
                f"[TASK_PERMANENT_FAILURE] Cancellation notification {notification.id} permanently failed: {exc}"
            )
            return {"status": "failed", "notification_id": notification.id, "error": str(exc)}

        countdown = 5 * (2 ** self.request.retries)
        logger.warning(
            f"[TASK_RETRY] Retrying cancellation task in {countdown}s (retry {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=3, name='notifications.send_appointment_reschedule')
def send_appointment_reschedule_task(self, new_appointment_id, original_appointment_id=None):
    """
    Asynchronous Celery task to dispatch an appointment reschedule notification.
    """
    logger.info(f"[TASK_START] Reschedule task started for new appointment {new_appointment_id}.")
    try:
        new_appointment = Appointment.objects.select_related(
            'patient',
            'patient__user',
            'doctor',
            'department',
        ).get(id=new_appointment_id)
    except Appointment.DoesNotExist:
        logger.error(f"[TASK_ERROR] Appointment {new_appointment_id} does not exist.")
        return {"status": "error", "message": "Appointment not found"}

    original_appointment = None
    if original_appointment_id:
        original_appointment = Appointment.objects.filter(id=original_appointment_id).first()

    recipient_email = NotificationService.get_recipient_email(new_appointment)
    if not recipient_email:
        logger.warning(f"[TASK_WARNING] No recipient email for appointment {new_appointment.reference}.")
        return {"status": "skipped", "message": "No recipient email"}

    subject, body = NotificationService.compose_reschedule_message(
        new_appointment, original_appointment
    )
    idempotency_key = f"RESCHEDULE_{new_appointment.id}"

    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'recipient': recipient_email,
            'recipient_user': new_appointment.patient.user if new_appointment.patient else None,
            'appointment': new_appointment,
            'notification_type': Notification.NotificationType.APPOINTMENT_RESCHEDULE,
            'channel': Notification.Channel.EMAIL,
            'status': Notification.Status.PENDING,
            'subject': subject,
            'message': body,
        },
    )

    if not created and notification.status == Notification.Status.SENT:
        logger.info(f"[TASK_ALREADY_SENT] Reschedule notification {notification.id} already SENT.")
        return {"status": "already_sent", "notification_id": notification.id}

    try:
        NotificationService.send_email_notification(notification.id)
        try:
            send_staff_alert_task.delay(new_appointment.id, "RESCHEDULED")
        except Exception as staff_alert_err:
            logger.warning(f"[STAFF_ALERT_FAILED] Failed to queue staff alert: {staff_alert_err}")

        return {"status": "sent", "notification_id": notification.id}

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            notification.status = Notification.Status.FAILED
            notification.failed_at = timezone.now()
            notification.error_message = f"Max retries ({self.max_retries}) exceeded: {exc}"
            notification.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
            logger.error(
                f"[TASK_PERMANENT_FAILURE] Reschedule notification {notification.id} permanently failed: {exc}"
            )
            return {"status": "failed", "notification_id": notification.id, "error": str(exc)}

        countdown = 5 * (2 ** self.request.retries)
        logger.warning(
            f"[TASK_RETRY] Retrying reschedule task in {countdown}s (retry {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=3, name='notifications.send_appointment_reminder')
def send_appointment_reminder_task(self, appointment_id):
    """
    Asynchronous Celery task to send a 24-hour appointment reminder.
    Verifies appointment is still CONFIRMED before dispatching.
    """
    logger.info(f"[TASK_START] Reminder task started for appointment {appointment_id}.")
    try:
        appointment = Appointment.objects.select_related(
            'patient',
            'patient__user',
            'doctor',
            'department',
        ).get(id=appointment_id)
    except Appointment.DoesNotExist:
        logger.error(f"[TASK_ERROR] Appointment {appointment_id} does not exist.")
        return {"status": "error", "message": "Appointment not found"}

    # Only send reminders for CONFIRMED appointments
    if appointment.status != Appointment.Status.CONFIRMED:
        logger.info(
            f"[TASK_REMINDER_SKIPPED] Appointment {appointment.reference} has status '{appointment.status}'. Skipping reminder."
        )
        return {"status": "skipped", "message": f"Appointment status is {appointment.status}"}

    recipient_email = NotificationService.get_recipient_email(appointment)
    if not recipient_email:
        return {"status": "skipped", "message": "No recipient email"}

    subject, body = NotificationService.compose_reminder_message(appointment)
    idempotency_key = f"REMINDER_{appointment.id}_{appointment.appointment_date}"

    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'recipient': recipient_email,
            'recipient_user': appointment.patient.user if appointment.patient else None,
            'appointment': appointment,
            'notification_type': Notification.NotificationType.APPOINTMENT_REMINDER,
            'channel': Notification.Channel.EMAIL,
            'status': Notification.Status.PENDING,
            'subject': subject,
            'message': body,
        },
    )

    if not created and notification.status == Notification.Status.SENT:
        logger.info(f"[TASK_ALREADY_SENT] Reminder notification {notification.id} already SENT.")
        return {"status": "already_sent", "notification_id": notification.id}

    try:
        NotificationService.send_email_notification(notification.id)
        return {"status": "sent", "notification_id": notification.id}

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            notification.status = Notification.Status.FAILED
            notification.failed_at = timezone.now()
            notification.error_message = f"Max retries ({self.max_retries}) exceeded: {exc}"
            notification.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
            logger.error(
                f"[TASK_PERMANENT_FAILURE] Reminder notification {notification.id} permanently failed: {exc}"
            )
            return {"status": "failed", "notification_id": notification.id, "error": str(exc)}

        countdown = 5 * (2 ** self.request.retries)
        logger.warning(
            f"[TASK_RETRY] Retrying reminder task in {countdown}s (retry {self.request.retries + 1}/{self.max_retries}): {exc}"
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=2, name='notifications.send_staff_alert')
def send_staff_alert_task(self, appointment_id, event_type="CREATED"):
    """
    Asynchronous Celery task to record an administrative alert notification
    for clinical / hospital staff oversight.
    """
    logger.info(f"[TASK_START] Staff alert task started for appointment {appointment_id} ({event_type}).")
    try:
        appointment = Appointment.objects.select_related('patient', 'doctor').get(id=appointment_id)
    except Appointment.DoesNotExist:
        return {"status": "error", "message": "Appointment not found"}

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hospitalplatform.local')
    subject, body = NotificationService.compose_staff_alert_message(appointment, event_type=event_type)
    idempotency_key = f"STAFF_ALERT_{event_type}_{appointment.id}"

    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'recipient': from_email,
            'appointment': appointment,
            'notification_type': Notification.NotificationType.ADMIN_ALERT,
            'channel': Notification.Channel.SYSTEM,
            'status': Notification.Status.SENT,
            'subject': subject,
            'message': body,
            'sent_at': timezone.now(),
        },
    )

    return {"status": "recorded", "notification_id": notification.id}


@shared_task(name='reminders.process_appointment_reminders')
def process_appointment_reminders_task():
    """
    Celery Beat periodic task: queries upcoming confirmed appointments for tomorrow
    in hospital timezone (Asia/Kolkata) and queues reminder notifications.
    Idempotent: Appointments with an existing reminder are skipped.
    """
    tz = ZoneInfo("Asia/Kolkata")
    now_in_tz = timezone.now().astimezone(tz)
    tomorrow_in_tz = now_in_tz.date() + timedelta(days=1)

    logger.info(f"[BEAT_REMINDER_CHECK] Scanning upcoming appointments for date {tomorrow_in_tz}.")

    eligible_appointments = Appointment.objects.filter(
        appointment_date=tomorrow_in_tz,
        status=Appointment.Status.CONFIRMED,
    ).select_related('patient', 'doctor')

    total_eligible = eligible_appointments.count()
    if total_eligible == 0:
        logger.info(f"[BEAT_REMINDER_CHECK] No eligible appointments found for {tomorrow_in_tz}.")
        return {"processed": 0, "queued": 0}

    # Find appointment IDs that already have a SENT or PENDING reminder
    already_reminded_ids = set(
        Notification.objects.filter(
            appointment__in=eligible_appointments,
            notification_type=Notification.NotificationType.APPOINTMENT_REMINDER,
            status__in=[Notification.Status.SENT, Notification.Status.PENDING],
        ).values_list('appointment_id', flat=True)
    )

    queued_count = 0
    for apt in eligible_appointments:
        if apt.id in already_reminded_ids:
            continue
        try:
            send_appointment_reminder_task.delay(apt.id)
            queued_count += 1
        except Exception as q_err:
            logger.error(f"[BEAT_REMINDER_QUEUE_ERROR] Failed to queue reminder for appointment {apt.id}: {q_err}")

    logger.info(
        f"[BEAT_REMINDER_COMPLETED] Processed {total_eligible} appointments, queued {queued_count} reminders."
    )
    return {"processed": total_eligible, "queued": queued_count}
