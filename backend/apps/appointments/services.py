from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from apps.appointments.models import Appointment
from apps.doctors.models import Doctor
from apps.scheduling.models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
from apps.accounts.models import User, PatientProfile
from apps.notifications.services import (
    safe_dispatch_confirmation,
    safe_dispatch_cancellation,
    safe_dispatch_reschedule,
)


class SlotConflictError(Exception):
    """Raised when a requested slot is unavailable or already booked to capacity (HTTP 409)."""
    pass


class SlotValidationError(Exception):
    """Raised when input parameters, dates, or shift bounds are invalid (HTTP 400)."""
    pass


class AppointmentStateError(Exception):
    """Raised when an invalid appointment lifecycle state transition is requested (HTTP 400)."""
    pass


class AppointmentBookingService:
    """
    Authoritative single-entry point for appointment booking, rescheduling,
    cancellation, and lifecycle management.
    Features:
    - Atomicity with transaction.atomic()
    - Row-level locking on Doctor with select_for_update() to serialize bookings
    - Full re-validation of leave, override, schedule, breaks, capacity, and past slots
    - Double-booking prevention
    - Idempotency support
    - Strict lifecycle transition validation
    """

    ALLOWED_TRANSITIONS = {
        Appointment.Status.REQUESTED: [
            Appointment.Status.CONFIRMED,
            Appointment.Status.CANCELLED,
        ],
        Appointment.Status.CONFIRMED: [
            Appointment.Status.CHECKED_IN,
            Appointment.Status.CANCELLED,
            Appointment.Status.NO_SHOW,
            Appointment.Status.RESCHEDULED,
        ],
        Appointment.Status.CHECKED_IN: [
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELLED,
        ],
        Appointment.Status.COMPLETED: [],
        Appointment.Status.CANCELLED: [],
        Appointment.Status.NO_SHOW: [],
        Appointment.Status.RESCHEDULED: [],
    }

    @classmethod
    def validate_transition(cls, current_status, new_status):
        """Validates if transitioning from current_status to new_status is allowed."""
        if current_status == new_status:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise AppointmentStateError(
                f"Invalid appointment status transition from '{current_status}' to '{new_status}'."
            )
        return True

    @classmethod
    def book_appointment(
        cls,
        patient,
        doctor,
        appointment_date,
        start_time,
        end_time,
        appointment_type=Appointment.AppointmentType.IN_PERSON,
        status=Appointment.Status.REQUESTED,
        reason_for_visit="",
        notes="",
        idempotency_key=None,
        rescheduled_from=None,
    ):
        """
        Creates an appointment transaction-safely with PostgreSQL row-level locking.
        Guarantees that two concurrent requests for the same doctor/date/slot cannot both succeed.
        """
        # Validate patient
        if not patient or not patient.is_active:
            raise SlotValidationError("Cannot book appointment for an inactive patient account.")

        # Check existing idempotency key
        if idempotency_key:
            existing = Appointment.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False

        # Parse date if string
        if isinstance(appointment_date, str):
            try:
                target_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
            except ValueError:
                raise SlotValidationError("Invalid date format. Expected YYYY-MM-DD.")
        else:
            target_date = appointment_date

        # Parse times if string
        if isinstance(start_time, str):
            try:
                t_parts = [int(p) for p in start_time.split(":")]
                start_t = time(*t_parts)
            except Exception:
                raise SlotValidationError("Invalid start_time format. Expected HH:MM or HH:MM:SS.")
        else:
            start_t = start_time

        if isinstance(end_time, str):
            try:
                t_parts = [int(p) for p in end_time.split(":")]
                end_t = time(*t_parts)
            except Exception:
                raise SlotValidationError("Invalid end_time format. Expected HH:MM or HH:MM:SS.")
        else:
            end_t = end_time

        if start_t >= end_t:
            raise SlotValidationError("Consultation end time must be after start time.")

        # ATOMIC TRANSACTION WITH ROW LOCKING
        with transaction.atomic():
            # Lock the Doctor row to serialize concurrent booking attempts for this doctor
            try:
                locked_doctor = (
                    Doctor.objects.select_for_update()
                    .select_related('department')
                    .get(id=doctor.id if hasattr(doctor, 'id') else doctor)
                )
            except Doctor.DoesNotExist:
                raise SlotValidationError("Doctor record not found.")

            if not locked_doctor.is_active:
                raise SlotValidationError("Cannot book consultation with an inactive doctor.")

            # Check planned leave
            if DoctorLeave.objects.filter(
                doctor=locked_doctor,
                is_active=True,
                start_date__lte=target_date,
                end_date__gte=target_date,
            ).exists():
                raise SlotConflictError("Doctor is on leave on the requested consultation date.")

            # Resolve schedule & overrides
            day_name = target_date.strftime("%A")
            schedule = (
                DoctorSchedule.objects.filter(
                    doctor=locked_doctor,
                    day_of_week=day_name,
                    is_active=True,
                )
                .prefetch_related('breaks')
                .first()
            )

            override = ScheduleOverride.objects.filter(
                doctor=locked_doctor,
                override_date=target_date,
            ).first()

            if override:
                if not override.is_available:
                    raise SlotConflictError(
                        f"Doctor is unavailable on this date ({override.reason or 'Schedule Override'})."
                    )
                shift_start = override.start_time or (schedule.start_time if schedule else None)
                shift_end = override.end_time or (schedule.end_time if schedule else None)
                slot_duration = (
                    override.slot_duration_minutes
                    or (schedule.slot_duration_minutes if schedule else locked_doctor.consultation_duration_minutes)
                    or 30
                )
                capacity = override.capacity or (schedule.capacity if schedule else 1)
            elif schedule:
                if not schedule.is_working_day:
                    raise SlotValidationError(f"{day_name} is a non-working day for this doctor.")
                shift_start = schedule.start_time
                shift_end = schedule.end_time
                slot_duration = schedule.slot_duration_minutes or locked_doctor.consultation_duration_minutes or 30
                capacity = schedule.capacity or 1
            else:
                raise SlotValidationError(f"No active schedule found for doctor on {day_name}.")

            if not shift_start or not shift_end:
                raise SlotValidationError("Shift working hours are not defined for this date.")

            # Validate shift bounds
            if start_t < shift_start or end_t > shift_end:
                raise SlotValidationError(
                    f"Requested consultation time ({start_t.strftime('%H:%M')} - {end_t.strftime('%H:%M')}) "
                    f"is outside doctor shift hours ({shift_start.strftime('%H:%M')} - {shift_end.strftime('%H:%M')})."
                )

            # Validate requested duration matches slot duration
            requested_delta = (
                datetime.combine(target_date, end_t) - datetime.combine(target_date, start_t)
            ).total_seconds() / 60
            if int(requested_delta) != slot_duration:
                raise SlotValidationError(
                    f"Invalid consultation slot duration ({int(requested_delta)} mins). "
                    f"Doctor schedule requires exactly {slot_duration} minutes per slot."
                )

            # Validate break overlap
            breaks = list(schedule.breaks.all()) if schedule else []
            for brk in breaks:
                if start_t < brk.end_time and end_t > brk.start_time:
                    raise SlotConflictError(
                        f"Requested slot overlaps with doctor scheduled break "
                        f"({brk.name}: {brk.start_time.strftime('%H:%M')} - {brk.end_time.strftime('%H:%M')})."
                    )

            # Validate timezone & past time protection
            resolved_tz_str = schedule.timezone if schedule else "Asia/Kolkata"
            try:
                tz = ZoneInfo(resolved_tz_str)
            except Exception:
                tz = ZoneInfo("Asia/Kolkata")

            now_in_tz = timezone.now().astimezone(tz)
            today_in_tz = now_in_tz.date()
            current_time_in_tz = now_in_tz.time()

            if target_date < today_in_tz:
                raise SlotValidationError("Cannot book an appointment for a past date.")

            if target_date == today_in_tz and start_t <= current_time_in_tz:
                raise SlotValidationError("Cannot book an appointment for a past time slot today.")

            # Query active booked appointments for this exact slot
            active_booked_count = (
                Appointment.objects.filter(
                    doctor=locked_doctor,
                    appointment_date=target_date,
                    start_time=start_t,
                    end_time=end_t,
                )
                .exclude(
                    status__in=[
                        Appointment.Status.CANCELLED,
                        Appointment.Status.RESCHEDULED,
                        Appointment.Status.NO_SHOW,
                    ]
                )
                .count()
            )

            # Enforce capacity
            if active_booked_count >= capacity:
                raise SlotConflictError("The selected appointment slot is no longer available.")

            # Create Appointment
            booking_status = status or Appointment.Status.REQUESTED
            appointment = Appointment.objects.create(
                patient=patient,
                doctor=locked_doctor,
                department=locked_doctor.department,
                consultation_location=locked_doctor.consultation_location,
                appointment_date=target_date,
                start_time=start_t,
                end_time=end_t,
                appointment_type=appointment_type,
                status=booking_status,
                reason_for_visit=reason_for_visit,
                notes=notes,
                idempotency_key=idempotency_key,
                rescheduled_from=rescheduled_from,
            )

            # Trigger asynchronous confirmation email only if confirmed
            if booking_status == Appointment.Status.CONFIRMED and not rescheduled_from:
                safe_dispatch_confirmation(appointment.id)

            return appointment, True

    @classmethod
    def cancel_appointment(cls, appointment_identifier, user, reason=""):
        """
        Cancels an appointment within an atomic transaction with row locking.
        """
        with transaction.atomic():
            qs = Appointment.objects.select_for_update().select_related('patient', 'doctor')
            if isinstance(appointment_identifier, Appointment):
                apt = qs.get(id=appointment_identifier.id)
            else:
                apt = qs.get(reference=appointment_identifier)

            # Check authorization: Patients can only cancel their own appointment
            if user.role == User.Role.PATIENT:
                if apt.patient.user_id != user.id:
                    raise PermissionDenied("You do not have permission to cancel this appointment.")

            # Validate lifecycle status
            allowed_cancellation_statuses = [
                Appointment.Status.REQUESTED,
                Appointment.Status.CONFIRMED,
                Appointment.Status.CHECKED_IN,
            ]
            if apt.status not in allowed_cancellation_statuses:
                raise AppointmentStateError(
                    f"Appointment with status '{apt.status}' cannot be cancelled."
                )

            apt.status = Appointment.Status.CANCELLED
            apt.cancelled_at = timezone.now()
            apt.cancellation_reason = reason or "Cancelled by patient/staff."
            apt.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])

            # Trigger asynchronous cancellation email after transaction commits
            safe_dispatch_cancellation(apt.id, apt.cancellation_reason)

            return apt

    @classmethod
    def reschedule_appointment(
        cls,
        appointment_identifier,
        user,
        new_date,
        new_start_time,
        new_end_time,
        reason="",
    ):
        """
        Reschedules an appointment atomically.
        If the new slot is unavailable or invalid, rolls back completely,
        leaving the original appointment unchanged.
        """
        with transaction.atomic():
            qs = Appointment.objects.select_for_update().select_related(
                'patient', 'doctor', 'department'
            )
            if isinstance(appointment_identifier, Appointment):
                original_apt = qs.get(id=appointment_identifier.id)
            else:
                original_apt = qs.get(reference=appointment_identifier)

            # Check authorization: Patients can only reschedule their own appointment
            if user.role == User.Role.PATIENT:
                if original_apt.patient.user_id != user.id:
                    raise PermissionDenied("You do not have permission to reschedule this appointment.")

            # Validate status
            allowed_reschedule_statuses = [
                Appointment.Status.REQUESTED,
                Appointment.Status.CONFIRMED,
            ]
            if original_apt.status not in allowed_reschedule_statuses:
                raise AppointmentStateError(
                    f"Appointment with status '{original_apt.status}' cannot be rescheduled."
                )

            # Mark original appointment as RESCHEDULED to release its slot before booking new one
            # Note: in atomic transaction, if the booking fails, this change is rolled back!
            prior_status = original_apt.status
            original_apt.status = Appointment.Status.RESCHEDULED
            original_apt.save(update_fields=['status', 'updated_at'])

            # Book new appointment
            new_apt, _ = cls.book_appointment(
                patient=original_apt.patient,
                doctor=original_apt.doctor,
                appointment_date=new_date,
                start_time=new_start_time,
                end_time=new_end_time,
                appointment_type=original_apt.appointment_type,
                status=Appointment.Status.CONFIRMED if prior_status == Appointment.Status.CONFIRMED else Appointment.Status.REQUESTED,
                reason_for_visit=original_apt.reason_for_visit,
                notes=f"Rescheduled from {original_apt.reference}. {reason}".strip(),
                rescheduled_from=original_apt,
            )

            # Trigger asynchronous reschedule email after transaction commits
            safe_dispatch_reschedule(new_apt.id, original_apt.id)

            return new_apt
