import uuid
from datetime import datetime
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


def generate_appointment_reference():
    """
    Generates a unique, stable, customer-facing appointment reference code.
    Format: APT-YYYY-XXXXXX (e.g. APT-2026-E4F92B)
    """
    year = datetime.now().year
    suffix = uuid.uuid4().hex[:6].upper()
    return f"APT-{year}-{suffix}"


class Appointment(models.Model):
    """
    Core outpatient appointment consultation record.
    Tracks patient, consultant doctor, department, consultation slot,
    and PDF lifecycle states.
    """
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', _('Requested (Pending Review)')
        CONFIRMED = 'CONFIRMED', _('Confirmed (Slot Booked)')
        CHECKED_IN = 'CHECKED_IN', _('Checked In (At OPD Desk)')
        COMPLETED = 'COMPLETED', _('Completed (Consultation Finished)')
        CANCELLED = 'CANCELLED', _('Cancelled')
        NO_SHOW = 'NO_SHOW', _('No Show (Patient Missed Slot)')
        RESCHEDULED = 'RESCHEDULED', _('Rescheduled')

    class AppointmentType(models.TextChoices):
        IN_PERSON = 'IN_PERSON', _('In-Person OPD Consultation')
        VIDEO = 'VIDEO', _('Telehealth Video Consultation')

    reference = models.CharField(
        _('appointment reference'),
        max_length=32,
        unique=True,
        db_index=True,
        default=generate_appointment_reference,
        help_text=_('Unique public consultation reference, e.g. APT-2026-1011'),
    )
    patient = models.ForeignKey(
        'accounts.PatientProfile',
        on_delete=models.PROTECT,
        related_name='appointments',
        help_text=_('Associated patient outpatient record.'),
    )
    doctor = models.ForeignKey(
        'doctors.Doctor',
        on_delete=models.PROTECT,
        related_name='appointments',
        help_text=_('Assigned consultant physician.'),
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='appointments',
        help_text=_('Clinical hospital department.'),
    )
    appointment_date = models.DateField(
        _('consultation date'),
        db_index=True,
    )
    start_time = models.TimeField(_('consultation start time'))
    end_time = models.TimeField(_('consultation end time'))
    appointment_type = models.CharField(
        _('consultation modality'),
        max_length=20,
        choices=AppointmentType.choices,
        default=AppointmentType.IN_PERSON,
    )
    consultation_location = models.CharField(
        _('consultation suite / room location'),
        max_length=200,
        blank=True,
    )
    status = models.CharField(
        _('lifecycle status'),
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    reason_for_visit = models.TextField(
        _('reason for consultation'),
        blank=True,
        help_text=_('Symptoms, checkup goals, or clinical referral notes.'),
    )
    notes = models.TextField(
        _('administrative / clinical notes'),
        blank=True,
        help_text=_('Reception check-in remarks or preliminary triage entries.'),
    )
    cancellation_reason = models.TextField(_('cancellation rationale'), blank=True)
    cancelled_at = models.DateTimeField(_('timestamp cancelled'), null=True, blank=True)
    rescheduled_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rescheduled_to',
        help_text=_('Prior appointment reference if this was rescheduled.'),
    )
    idempotency_key = models.CharField(
        _('idempotency key'),
        max_length=128,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text=_('Unique client request key to prevent duplicate booking transactions.'),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('appointment')
        verbose_name_plural = _('appointments')
        ordering = ['-appointment_date', '-start_time']
        indexes = [
            models.Index(fields=['appointment_date', 'status'], name='idx_apt_date_status'),
            models.Index(fields=['doctor', 'appointment_date'], name='idx_apt_doctor_date'),
            models.Index(fields=['patient', 'appointment_date'], name='idx_apt_patient_date'),
            models.Index(fields=['department', 'appointment_date'], name='idx_apt_dept_date'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')),
                name='apt_end_time_after_start_time',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_appointment_reference()
        if not self.department_id and self.doctor_id and self.doctor.department_id:
            self.department = self.doctor.department
        if not self.consultation_location and self.doctor_id:
            self.consultation_location = self.doctor.consultation_location
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_('Consultation end time must be after start time.'))

    def __str__(self):
        return f"{self.reference} - {self.patient.full_name} with {self.doctor.name} on {self.appointment_date} ({self.get_status_display()})"
