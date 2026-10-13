from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Notification(models.Model):
    """
    Outbound communication log for SMS, Email, and System alerts.
    Tracking for appointment confirmations, reminders, and alerts.
    """
    class NotificationType(models.TextChoices):
        APPOINTMENT_CONFIRMATION = 'APPOINTMENT_CONFIRMATION', _('Appointment Confirmation')
        APPOINTMENT_REMINDER = 'APPOINTMENT_REMINDER', _('Appointment Reminder')
        APPOINTMENT_CANCELLATION = 'APPOINTMENT_CANCELLATION', _('Appointment Cancellation')
        APPOINTMENT_RESCHEDULE = 'APPOINTMENT_RESCHEDULE', _('Appointment Reschedule')
        ADMIN_ALERT = 'ADMIN_ALERT', _('Administrative System Alert')

    class Channel(models.TextChoices):
        EMAIL = 'EMAIL', _('Email')
        SMS = 'SMS', _('SMS Gateway')
        SYSTEM = 'SYSTEM', _('System Desk')

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        SENT = 'SENT', _('Sent')
        FAILED = 'FAILED', _('Failed')

    recipient = models.CharField(
        _('recipient identifier'),
        max_length=255,
        help_text=_('Recipient phone number, email address, or administrative desk name.'),
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    notification_type = models.CharField(
        _('notification category'),
        max_length=35,
        choices=NotificationType.choices,
        db_index=True,
    )
    channel = models.CharField(
        _('dispatch channel'),
        max_length=15,
        choices=Channel.choices,
        default=Channel.SMS,
    )
    status = models.CharField(
        _('delivery status'),
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    subject = models.CharField(_('subject / headline'), max_length=255, blank=True)
    message = models.TextField(_('message payload content'))
    provider_reference = models.CharField(
        _('external gateway message ID'),
        max_length=128,
        blank=True,
    )
    retry_count = models.PositiveIntegerField(
        _('retry attempt count'),
        default=0,
        help_text=_('Number of dispatch retry attempts performed.'),
    )
    error_message = models.TextField(
        _('last error message'),
        blank=True,
        help_text=_('Failure reason or exception message if dispatch encountered an error.'),
    )
    idempotency_key = models.CharField(
        _('idempotency key'),
        max_length=128,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text=_('Unique key preventing duplicate notification processing.'),
    )
    sent_at = models.DateTimeField(_('timestamp dispatched'), null=True, blank=True)
    failed_at = models.DateTimeField(_('timestamp failed'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_channel_display()}] {self.get_notification_type_display()} to {self.recipient} ({self.get_status_display()})"


class AuditLog(models.Model):
    """
    Administrative and clinical activity audit trail.
    Provides non-repudiation and traceability across system modifications.
    """
    class Result(models.TextChoices):
        SUCCESS = 'SUCCESS', _('Success')
        WARNING = 'WARNING', _('Warning')
        DENIED = 'DENIED', _('Denied')

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    actor_name = models.CharField(
        _('actor display name'),
        max_length=150,
        blank=True,
        help_text=_('Cached name or system process identifier.'),
    )
    role = models.CharField(_('actor role at execution'), max_length=64, blank=True)
    action = models.CharField(
        _('action code'),
        max_length=100,
        db_index=True,
        help_text=_('e.g. DOCTOR_UPDATED, APPOINTMENT_STATUS_CHANGED, PATIENT_RECORD_ACCESSED'),
    )
    resource_type = models.CharField(
        _('target resource entity'),
        max_length=64,
        db_index=True,
    )
    resource_id = models.CharField(
        _('target entity primary key or reference'),
        max_length=128,
        db_index=True,
    )
    result = models.CharField(
        _('action outcome'),
        max_length=15,
        choices=Result.choices,
        default=Result.SUCCESS,
        db_index=True,
    )
    details = models.TextField(_('narrative description of change'), blank=True)
    metadata = models.JSONField(
        _('structured event context'),
        default=dict,
        blank=True,
    )
    ip_address = models.GenericIPAddressField(_('client IP address'), null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('audit log entry')
        verbose_name_plural = _('audit log entries')
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.actor_name or 'System'}: {self.action} on {self.resource_type}:{self.resource_id} ({self.result})"
