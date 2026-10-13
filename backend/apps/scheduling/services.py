from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone
from apps.scheduling.models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
from apps.appointments.models import Appointment
from apps.doctors.models import Doctor


class AvailabilityEngine:
    """
    Authoritative backend engine for calculating doctor slot availability.
    Takes into account:
    - Doctor active status
    - Working days & working hours (DoctorSchedule)
    - Schedule overrides (ScheduleOverride)
    - Doctor planned leave (DoctorLeave)
    - Shift recess & clinical breaks (ScheduleBreak)
    - Configured slot duration & capacity
    - Doctor operating timezone
    - Already booked active appointments
    - Past time protection
    """

    @classmethod
    def get_doctor_availability(cls, doctor, query_date, tz_name=None):
        """
        Calculates and returns deterministic consultation slots for a given doctor and date.
        """
        if not doctor or not doctor.is_active:
            return {
                "doctor": {"id": getattr(doctor, 'id', None), "name": getattr(doctor, 'name', '')},
                "date": str(query_date),
                "timezone": tz_name or "Asia/Kolkata",
                "slot_duration_minutes": 30,
                "available_slots": [],
                "reason": "Doctor is inactive or not found.",
            }

        # Normalize date
        if isinstance(query_date, str):
            try:
                target_date = datetime.strptime(query_date, "%Y-%m-%d").date()
            except ValueError:
                return {
                    "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                    "date": query_date,
                    "timezone": tz_name or "Asia/Kolkata",
                    "slot_duration_minutes": 30,
                    "available_slots": [],
                    "reason": "Invalid date format. Expected YYYY-MM-DD.",
                }
        else:
            target_date = query_date

        # Resolve day name (e.g. 'Monday', 'Tuesday')
        day_name = target_date.strftime("%A")

        # Resolve weekly schedule
        schedule = (
            DoctorSchedule.objects.filter(
                doctor=doctor,
                day_of_week=day_name,
                is_active=True,
            )
            .prefetch_related('breaks')
            .first()
        )

        # Resolve operating timezone
        resolved_tz_str = tz_name or (schedule.timezone if schedule else "Asia/Kolkata")
        try:
            tz = ZoneInfo(resolved_tz_str)
        except Exception:
            tz = ZoneInfo("Asia/Kolkata")
            resolved_tz_str = "Asia/Kolkata"

        now_in_tz = timezone.now().astimezone(tz)
        today_in_tz = now_in_tz.date()
        current_time_in_tz = now_in_tz.time()

        # Reject query date strictly in the past
        if target_date < today_in_tz:
            return {
                "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                "date": str(target_date),
                "timezone": resolved_tz_str,
                "slot_duration_minutes": 30,
                "available_slots": [],
                "reason": "Selected date is in the past.",
            }

        # Check planned leave
        is_on_leave = DoctorLeave.objects.filter(
            doctor=doctor,
            is_active=True,
            start_date__lte=target_date,
            end_date__gte=target_date,
        ).exists()

        if is_on_leave:
            return {
                "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                "date": str(target_date),
                "timezone": resolved_tz_str,
                "slot_duration_minutes": 30,
                "available_slots": [],
                "reason": "Doctor is on leave on this date.",
            }

        # Check date-specific override
        override = ScheduleOverride.objects.filter(
            doctor=doctor,
            override_date=target_date,
        ).first()

        # If override marks doctor unavailable
        if override and not override.is_available:
            return {
                "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                "date": str(target_date),
                "timezone": resolved_tz_str,
                "slot_duration_minutes": 30,
                "available_slots": [],
                "reason": f"Doctor is unavailable on this date ({override.reason or 'Schedule Override'}).",
            }

        # If no override, verify weekly schedule working day
        if not override:
            if not schedule or not schedule.is_working_day:
                return {
                    "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                    "date": str(target_date),
                    "timezone": resolved_tz_str,
                    "slot_duration_minutes": 30,
                    "available_slots": [],
                    "reason": f"{day_name} is a non-working day for this doctor.",
                }

        # Determine shift working parameters
        start_time = None
        end_time = None
        slot_duration = 30
        capacity = 1

        if override:
            start_time = override.start_time or (schedule.start_time if schedule else None)
            end_time = override.end_time or (schedule.end_time if schedule else None)
            slot_duration = (
                override.slot_duration_minutes
                or (schedule.slot_duration_minutes if schedule else doctor.consultation_duration_minutes)
                or 30
            )
            capacity = override.capacity or (schedule.capacity if schedule else 1)
        elif schedule:
            start_time = schedule.start_time
            end_time = schedule.end_time
            slot_duration = schedule.slot_duration_minutes or doctor.consultation_duration_minutes or 30
            capacity = schedule.capacity or 1

        if not start_time or not end_time or start_time >= end_time:
            return {
                "doctor": {"id": doctor.id, "name": doctor.name, "slug": doctor.slug},
                "date": str(target_date),
                "timezone": resolved_tz_str,
                "slot_duration_minutes": slot_duration,
                "available_slots": [],
                "reason": "No valid working hours defined for this date.",
            }

        # Fetch scheduled breaks
        breaks = list(schedule.breaks.all()) if schedule else []

        # Fetch existing active appointments for doctor on target date
        active_appointments = Appointment.objects.filter(
            doctor=doctor,
            appointment_date=target_date,
        ).exclude(
            status__in=[
                Appointment.Status.CANCELLED,
                Appointment.Status.RESCHEDULED,
                Appointment.Status.NO_SHOW,
            ]
        ).values_list('start_time', 'end_time')

        # Count booked appointments per slot
        booked_counts = {}
        for apt_start, apt_end in active_appointments:
            slot_key = (apt_start, apt_end)
            booked_counts[slot_key] = booked_counts.get(slot_key, 0) + 1

        # Generate discrete slots
        slots = []
        cur_dt = datetime.combine(target_date, start_time)
        shift_end_dt = datetime.combine(target_date, end_time)
        delta = timedelta(minutes=slot_duration)

        while cur_dt + delta <= shift_end_dt:
            slot_start_time = cur_dt.time()
            slot_end_time = (cur_dt + delta).time()

            # Check break intersection
            in_break = False
            for brk in breaks:
                # Overlap condition: start < break.end and end > break.start
                if slot_start_time < brk.end_time and slot_end_time > brk.start_time:
                    in_break = True
                    break

            # Check if past slot (for today)
            is_past = False
            if target_date == today_in_tz:
                if slot_start_time <= current_time_in_tz:
                    is_past = True

            # Check booked capacity
            current_bookings = booked_counts.get((slot_start_time, slot_end_time), 0)
            is_full = current_bookings >= capacity

            available = not in_break and not is_past and not is_full
            slot_status = "available" if available else ("break" if in_break else ("past" if is_past else ("booked" if is_full else "unavailable")))
            slot_reason = None if available else ("Clinical Break" if in_break else ("Past Time" if is_past else ("Booked to Capacity" if is_full else "Unavailable")))

            slots.append({
                "start_time": slot_start_time.strftime("%H:%M:%S"),
                "end_time": slot_end_time.strftime("%H:%M:%S"),
                "available": available,
                "status": slot_status,
                "reason": slot_reason,
            })

            cur_dt += delta

        return {
            "doctor": {
                "id": doctor.id,
                "name": doctor.name,
                "slug": doctor.slug,
            },
            "date": str(target_date),
            "timezone": resolved_tz_str,
            "slot_duration_minutes": slot_duration,
            "capacity_per_slot": capacity,
            "available_slots": slots,
        }

    @classmethod
    def get_doctor_availability_range(cls, doctor, start_date, end_date, tz_name=None):
        """
        Calculates and returns deterministic consultation availability for a range of dates.
        """
        if not doctor or not doctor.is_active:
            return {
                "doctor": {"id": getattr(doctor, 'id', None), "name": getattr(doctor, 'name', '')},
                "timezone": tz_name or "Asia/Kolkata",
                "dates": [],
                "reason": "Doctor is inactive or not found.",
            }

        if isinstance(start_date, str):
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                start_dt = date.today()
        else:
            start_dt = start_date

        if isinstance(end_date, str):
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                end_dt = start_dt + timedelta(days=10)
        else:
            end_dt = end_date

        if end_dt < start_dt:
            end_dt = start_dt + timedelta(days=10)

        # Cap range at 30 days maximum
        if (end_dt - start_dt).days > 30:
            end_dt = start_dt + timedelta(days=30)

        date_results = []
        curr = start_dt
        resolved_tz = tz_name or "Asia/Kolkata"

        while curr <= end_dt:
            day_data = cls.get_doctor_availability(doctor, curr, tz_name=tz_name)
            resolved_tz = day_data.get("timezone", resolved_tz)
            is_working = False
            status_text = "Unavailable"
            status_type = "closed"
            is_selectable = False

            slots = day_data.get("available_slots", [])
            open_slots_count = sum(1 for s in slots if s.get("available"))
            reason = day_data.get("reason")

            if "on leave" in (reason or "").lower():
                status_text = "On Leave"
                status_type = "leave"
            elif "override" in (reason or "").lower():
                status_text = "Special OPD"
                status_type = "override"
                is_selectable = open_slots_count > 0
            elif open_slots_count > 0:
                status_text = "Available"
                status_type = "available"
                is_selectable = True
                is_working = True
            elif slots:
                status_text = "Fully Booked"
                status_type = "booked"
                is_working = True
            else:
                status_text = "Clinic Closed"
                status_type = "closed"

            date_results.append({
                "date": str(curr),
                "day_name": curr.strftime("%A"),
                "is_working_day": is_working,
                "status": status_text,
                "status_type": status_type,
                "is_selectable": is_selectable,
                "open_slots_count": open_slots_count,
                "total_slots_count": len(slots),
                "reason": reason,
                "available_slots": slots,
            })
            curr += timedelta(days=1)

        return {
            "doctor": {
                "id": doctor.id,
                "name": doctor.name,
                "slug": doctor.slug,
            },
            "timezone": resolved_tz,
            "start_date": str(start_dt),
            "end_date": str(end_dt),
            "dates": date_results,
        }
