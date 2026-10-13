import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.doctors.models import Doctor, Specialty
from apps.departments.models import Department
from apps.scheduling.models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
from apps.appointments.models import Appointment
from apps.accounts.models import PatientProfile

print("=== DOCTORS ===")
for d in Doctor.objects.all():
    print(f"ID {d.id}: {d.name} | Slug: {d.slug} | Active: {d.is_active} | Dept: {d.department} | Specialty: {d.specialty}")

print("\n=== SCHEDULES (SAMPLE) ===")
for s in DoctorSchedule.objects.all()[:10]:
    breaks = list(s.breaks.values_list('start_time', 'end_time'))
    print(f"Doc {s.doctor_id} ({s.doctor.name}): Day {s.day_of_week} | {s.start_time} - {s.end_time} | Slot: {s.slot_duration_minutes}m | Active: {s.is_active} | Breaks: {breaks}")

print("\n=== APPOINTMENTS ===")
for a in Appointment.objects.all():
    print(f"Ref {a.reference}: Doc {a.doctor.name} | Date {a.appointment_date} | Slot {a.start_time}-{a.end_time} | Status: {a.status} | Patient: {a.patient_name} ({a.patient_email})")

print("\n=== PATIENT PROFILES ===")
for p in PatientProfile.objects.all():
    print(f"MRN {p.mrn}: {p.first_name} {p.last_name} | Email: {p.email} | Phone: {p.phone} | User: {p.user}")
