from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class DoctorSchedule(models.Model):
    """
    Weekly recurrent shift allocation for a doctor.
    Defines working days, standard OPD hours, slot duration, capacity, and timezone.
    """
    class DayOfWeek(models.TextChoices):
        MONDAY = 'Monday', _('Monday')
        TUESDAY = 'Tuesday', _('Tuesday')
        WEDNESDAY = 'Wednesday', _('Wednesday')
        THURSDAY = 'Thursday', _('Thursday')
        FRIDAY = 'Friday', _('Friday')
        SATURDAY = 'Saturday', _('Saturday')
        SUNDAY = 'Sunday', _('Sunday')

    doctor = models.ForeignKey(
        'doctors.Doctor',
        on_delete=models.CASCADE,
        related_name='schedules',
    )
    day_of_week = models.CharField(
        _('day of the week'),
        max_length=15,
        choices=DayOfWeek.choices,
    )
    start_time = models.TimeField(_('shift start time'))
    end_time = models.TimeField(_('shift end time'))
    slot_duration_minutes = models.PositiveIntegerField(
        _('slot duration (minutes)'),
        default=30,
        help_text=_('Length of each outpatient consultation slot.'),
    )
    capacity = models.PositiveIntegerField(
        _('patient capacity per slot'),
        default=1,
        help_text=_('Maximum patients allowable per discrete time slot.'),
    )
    timezone = models.CharField(
        _('timezone'),
        max_length=64,
        default='Asia/Kolkata',
        help_text=_('Consultant schedule operating timezone.'),
    )
    is_working_day = models.BooleanField(_('is working day'), default=True)
    is_active = models.BooleanField(_('active schedule'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('doctor schedule')
        verbose_name_plural = _('doctor schedules')
        ordering = ['doctor', 'day_of_week']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'day_of_week'],
                name='unique_doctor_day_schedule',
            ),
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')),
                name='schedule_end_time_after_start_time',
            ),
            models.CheckConstraint(
                condition=Q(slot_duration_minutes__gt=0),
                name='positive_slot_duration',
            ),
            models.CheckConstraint(
                condition=Q(capacity__gt=0),
                name='positive_slot_capacity',
            ),

        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_('Shift end time must be later than start time.'))

    def __str__(self):
        status = "Working" if self.is_working_day else "Off"
        return f"{self.doctor.name} - {self.day_of_week} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}) [{status}]"


class ScheduleBreak(models.Model):
    """
    Midday recesses, ward rounds, or breaks within a doctor's weekly shift.
    """
    schedule = models.ForeignKey(
        DoctorSchedule,
        on_delete=models.CASCADE,
        related_name='breaks',
    )
    name = models.CharField(_('break description'), max_length=100, default='Clinical Break')
    start_time = models.TimeField(_('break start time'))
    end_time = models.TimeField(_('break end time'))

    class Meta:
        verbose_name = _('schedule break')
        verbose_name_plural = _('schedule breaks')
        ordering = ['start_time']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F('start_time')),
                name='break_end_time_after_start_time',
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_('Break end time must be later than start time.'))

    def __str__(self):
        return f"{self.name}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class DoctorLeave(models.Model):
    """
    Planned doctor absence (annual leave, conference, academic duty).
    Blocks slot availability during the specified date range.
    """
    doctor = models.ForeignKey(
        'doctors.Doctor',
        on_delete=models.CASCADE,
        related_name='leaves',
    )
    start_date = models.DateField(_('leave start date'))
    end_date = models.DateField(_('leave end date'))
    reason = models.CharField(_('reason for leave'), max_length=255)
    is_active = models.BooleanField(_('active status'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('doctor leave')
        verbose_name_plural = _('doctor leaves')
        ordering = ['start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F('start_date')),
                name='leave_end_date_gte_start_date',
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_('Leave end date cannot precede start date.'))

    def __str__(self):
        return f"{self.doctor.name} Leave: {self.start_date} to {self.end_date} ({self.reason})"


class ScheduleOverride(models.Model):
    """
    Date-specific schedule override (e.g. special weekend clinic, adjusted hours, or holiday cover).
    """
    class OverrideType(models.TextChoices):
        SPECIAL_OPD = 'SPECIAL_OPD', _('Special OPD')
        EXTENDED_HOURS = 'EXTENDED_HOURS', _('Extended Hours')
        REDUCED_HOURS = 'REDUCED_HOURS', _('Reduced Hours')
        CLOSED = 'CLOSED', _('Closed')
        UNAVAILABLE = 'UNAVAILABLE', _('Doctor Unavailable')
        SHIFT_ADJUSTMENT = 'SHIFT_ADJUSTMENT', _('Shift Time Adjustment')
        EMERGENCY_COVER = 'EMERGENCY_COVER', _('Emergency Roster Cover')

    doctor = models.ForeignKey(
        'doctors.Doctor',
        on_delete=models.CASCADE,
        related_name='overrides',
    )
    override_date = models.DateField(_('override date'), db_index=True)
    override_type = models.CharField(
        _('override type'),
        max_length=30,
        choices=OverrideType.choices,
        default=OverrideType.SPECIAL_OPD,
    )
    is_available = models.BooleanField(
        _('available for booking'),
        default=True,
        help_text=_('Set to False to close bookings on this date entirely.'),
    )
    start_time = models.TimeField(_('custom start time'), null=True, blank=True)
    end_time = models.TimeField(_('custom end time'), null=True, blank=True)
    slot_duration_minutes = models.PositiveIntegerField(
        _('custom slot duration'),
        null=True,
        blank=True,
    )
    capacity = models.PositiveIntegerField(
        _('custom slot capacity'),
        null=True,
        blank=True,
    )
    reason = models.CharField(_('reason / notes'), max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('schedule override')
        verbose_name_plural = _('schedule overrides')
        ordering = ['override_date']

    def clean(self):
        super().clean()
        if self.override_type in (self.OverrideType.CLOSED, self.OverrideType.UNAVAILABLE):
            self.is_available = False
            self.start_time = None
            self.end_time = None
        elif self.is_available:
            if self.start_time and self.end_time and self.start_time >= self.end_time:
                raise ValidationError({'end_time': _('Override end time must be later than start time.')})

    def __str__(self):
        return f"{self.doctor.name} Override on {self.override_date} ({self.get_override_type_display()})"
