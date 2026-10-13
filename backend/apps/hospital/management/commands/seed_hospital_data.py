"""
Management command to idempotently seed verified clinical hospital data into PostgreSQL.
Seeds HospitalProfile, Department, Specialty, Doctor, and DoctorSchedule records.
Safe to run repeatedly; does not duplicate records.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
import datetime

from apps.hospital.models import HospitalProfile
from apps.departments.models import Department
from apps.doctors.models import Specialty, Doctor
from apps.scheduling.models import DoctorSchedule, ScheduleBreak

User = get_user_model()


class Command(BaseCommand):
    help = "Idempotently seeds initial clinical departments, specialties, doctors, and schedules into PostgreSQL."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Seeding Eagle Sora Hospital Clinical Data ==="))

        with transaction.atomic():
            # 1. Hospital Profile
            profile, created = HospitalProfile.objects.get_or_create(
                id=1,
                defaults={
                    'name': 'EgleSora Hospital',
                    'legal_name': 'EgleSora Memorial Hospital & Research Institute',
                    'tagline': 'Excellence in Clinical Care & Patient Safety',
                    'overview': 'Established healthcare institution delivering compassionate outpatient, inpatient, and emergency clinical medical services.',
                    'contact_phone': '+91 (0) 22 0000 2222',
                    'emergency_phone': '+91 (0) 22 0000 1111',
                    'contact_email': 'desk@eglesorahospital.org',
                    'address': '12 Medical District Avenue, City Center',
                    'visiting_hours': 'Monday - Saturday: 08:00 AM - 08:00 PM',
                    'emergency_info': '24/7 dedicated acute trauma triage and emergency ambulance dispatch.',
                    'is_active': True,
                }
            )
            self.stdout.write(f"Hospital Profile: {profile.name} (Created: {created})")

            # 2. Specialties
            specialties_data = [
                ('Cardiology', 'cardiology', 'Diagnostic and interventional cardiovascular medicine and preventive cardiology.'),
                ('Neurology', 'neurology', 'Comprehensive stroke management, epilepsy care, and neuromuscular diagnostics.'),
                ('Orthopaedics', 'orthopaedics', 'Joint reconstruction, spine assessment, arthroscopy, and trauma surgery.'),
                ('Medical Oncology', 'oncology', 'Medical cancer management, precision chemotherapy, and targeted biological therapies.'),
                ('Paediatrics', 'paediatrics', 'General paediatric healthcare, newborn care, developmental surveillance, and immunisation.'),
                ('Emergency Medicine', 'emergency-medicine', 'Acute resuscitation, trauma care, and 24/7 emergency response protocols.'),
                ('Gastroenterology', 'gastroenterology', 'Digestive health, clinical hepatology, and therapeutic endoscopy.'),
                ('Nephrology', 'nephrology', 'Renal medicine, dialysis management, and hypertension assessment.'),
            ]

            spec_map = {}
            for name, slug, desc in specialties_data:
                spec, _ = Specialty.objects.get_or_create(
                    slug=slug,
                    defaults={'name': name, 'description': desc, 'is_active': True}
                )
                spec_map[slug] = spec

            self.stdout.write(f"Specialties seeded: {len(spec_map)}")

            # 3. Clinical Departments
            depts_data = [
                {
                    'name': 'Cardiology & Vascular Medicine',
                    'slug': 'cardiology',
                    'specialty': 'Cardiovascular Care',
                    'short_description': 'Comprehensive diagnostic and interventional cardiac care, cardiovascular prevention, and electrophysiology.',
                    'full_description': 'Dedicated tertiary cardiac care center providing outpatient consultations, non-invasive imaging, and advanced vascular management.',
                    'opd_hours': 'Mon - Sat: 08:30 AM - 05:00 PM',
                    'location': 'Wing B, 2nd Floor, Suite 201-208',
                    'contact_phone': '+91 (0) 22 0000 2201',
                    'contact_email': 'cardiology@eglesorahospital.org',
                },
                {
                    'name': 'Neurology & Neurosurgery',
                    'slug': 'neurology',
                    'specialty': 'Neurosciences',
                    'short_description': 'Specialized management of cerebrovascular diseases, epilepsy, peripheral neuropathy, and neurological emergencies.',
                    'full_description': 'State-of-the-art neurosciences pavilion offering comprehensive stroke management and clinical neurology.',
                    'opd_hours': 'Mon - Fri: 09:00 AM - 04:30 PM',
                    'location': 'Wing A, 3rd Floor, Suite 301-306',
                    'contact_phone': '+91 (0) 22 0000 2202',
                    'contact_email': 'neurology@eglesorahospital.org',
                },
                {
                    'name': 'Orthopaedics & Joint Surgery',
                    'slug': 'orthopaedics',
                    'specialty': 'Musculoskeletal Disorders',
                    'short_description': 'Joint replacement, arthroscopy, sports trauma, spine assessment, and rehabilitation.',
                    'full_description': 'Advanced orthopaedic center for joint reconstruction, arthroscopy, and musculoskeletal trauma.',
                    'opd_hours': 'Mon - Sat: 09:00 AM - 05:00 PM',
                    'location': 'Wing C, 1st Floor, Suite 101-107',
                    'contact_phone': '+91 (0) 22 0000 2203',
                    'contact_email': 'ortho@eglesorahospital.org',
                },
                {
                    'name': 'Medical Oncology',
                    'slug': 'oncology',
                    'specialty': 'Cancer Care',
                    'short_description': 'Multidisciplinary cancer management, precision chemotherapy, and targeted clinical therapies.',
                    'full_description': 'Comprehensive cancer institute providing compassionate oncological care and patient support.',
                    'opd_hours': 'Mon - Fri: 09:00 AM - 04:00 PM',
                    'location': 'Wing D, 4th Floor, Suite 401-410',
                    'contact_phone': '+91 (0) 22 0000 2204',
                    'contact_email': 'oncology@eglesorahospital.org',
                },
                {
                    'name': 'Paediatrics & Neonatology',
                    'slug': 'paediatrics',
                    'specialty': 'Child Health & Newborn Care',
                    'short_description': 'Primary and specialist paediatric consultations, developmental reviews, and immunization schedules.',
                    'full_description': 'Family-centered pediatric and neonatal clinic with child-friendly clinical environments.',
                    'opd_hours': 'Mon - Sat: 08:30 AM - 06:00 PM',
                    'location': 'Wing B, 1st Floor, Suite 111-118',
                    'contact_phone': '+91 (0) 22 0000 2205',
                    'contact_email': 'pediatrics@eglesorahospital.org',
                },
                {
                    'name': 'Emergency & Critical Care Medicine',
                    'slug': 'emergency',
                    'specialty': 'Trauma & Resuscitation',
                    'short_description': '24/7 dedicated acute emergency trauma facility with immediate triage and resuscitation suites.',
                    'full_description': 'Level-1 tertiary emergency facility equipped with dedicated resuscitation suites, point-of-care ultrasound, and rapid-response teams.',
                    'opd_hours': '24/7 Dedicated Emergency Services',
                    'location': 'Ground Floor, Emergency Pavilion',
                    'contact_phone': '+91 (0) 22 0000 1111',
                    'contact_email': 'emergency@eglesorahospital.org',
                },
            ]

            dept_map = {}
            for d in depts_data:
                dept, _ = Department.objects.get_or_create(
                    slug=d['slug'],
                    defaults=d
                )
                dept_map[d['slug']] = dept

            self.stdout.write(f"Departments seeded: {len(dept_map)}")

            # 4. Doctors
            doctor_user = User.objects.filter(email='doctor.varma@eglesorahospital.org').first()

            doctors_data = [
                {
                    'name': 'Dr. Rajesh K. Varma',
                    'slug': 'dr-rajesh-k-varma',
                    'department': dept_map['cardiology'],
                    'specialty': spec_map['cardiology'],
                    'specialty_name': 'Cardiology & Vascular Medicine',
                    'qualification': 'MBBS, MD (General Medicine), DM (Cardiology), FACC',
                    'experience_years': 18,
                    'bio': 'Senior Consultant and Head of Cardiology with 18 years of clinical leadership in diagnostic and interventional cardiovascular medicine.',
                    'expertise': 'Cardiovascular Diagnostics, Coronary Artery Disease, Hypertension, Lipid Management, Clinical Electrophysiology',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 30,
                    'consultation_location': 'Cardiology OPD, Wing B, 2nd Floor, Suite 204',
                    'is_active': True,
                    'user': doctor_user,
                },
                {
                    'name': 'Dr. Priya Nair',
                    'slug': 'dr-priya-nair',
                    'department': dept_map['neurology'],
                    'specialty': spec_map['neurology'],
                    'specialty_name': 'Neurology & Stroke Care',
                    'qualification': 'MBBS, MD (General Medicine), DM (Neurology)',
                    'experience_years': 14,
                    'bio': 'Consultant Neurologist specializing in comprehensive stroke management, clinical neuro-immunology, and neuromuscular disorders.',
                    'expertise': 'Acute Stroke Management, Headache Disorders, Epilepsy, Peripheral Neuropathy, Multiple Sclerosis',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 30,
                    'consultation_location': 'Neurology OPD, Wing A, 3rd Floor, Suite 302',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Amitav Ghosh',
                    'slug': 'dr-amitav-ghosh',
                    'department': dept_map['orthopaedics'],
                    'specialty': spec_map['orthopaedics'],
                    'specialty_name': 'Orthopaedics & Joint Surgery',
                    'qualification': 'MBBS, MS (Orthopaedics), MCh (Orth), FAOrthA',
                    'experience_years': 20,
                    'bio': 'Senior Consultant Orthopaedic Surgeon specializing in primary and revision joint arthroplasty and complex trauma reconstruction.',
                    'expertise': 'Total Knee Replacement, Hip Arthroplasty, Arthroscopic Knee Reconstruction, Sports Injuries',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 30,
                    'consultation_location': 'Orthopaedics OPD, Wing C, 1st Floor, Suite 104',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Sunita Kulkarni',
                    'slug': 'dr-sunita-kulkarni',
                    'department': dept_map['oncology'],
                    'specialty': spec_map['oncology'],
                    'specialty_name': 'Medical Oncology & Cancer Care',
                    'qualification': 'MBBS, MD (Radiotherapy), DM (Medical Oncology), ESMO Certified',
                    'experience_years': 15,
                    'bio': 'Senior Consultant Medical Oncologist with extensive clinical research in targeted molecular therapies and personalized systemic protocols.',
                    'expertise': 'Solid Tumor Oncology, Systemic Chemotherapy, Targeted Biological Therapies, Immuno-oncology',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 45,
                    'consultation_location': 'Oncology Daycare Wing, 4th Floor, Suite 405',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Rohan Deshmukh',
                    'slug': 'dr-rohan-deshmukh',
                    'department': dept_map['paediatrics'],
                    'specialty': spec_map['paediatrics'],
                    'specialty_name': 'Paediatrics & Neonatology',
                    'qualification': 'MBBS, MD (Paediatrics), DNB (Neonatology)',
                    'experience_years': 12,
                    'bio': 'Consultant Paediatrician committed to comprehensive child wellness, neonatal growth surveillance, and acute pediatric illness management.',
                    'expertise': 'General Paediatrics, Neonatal Care, Developmental Assessment, Childhood Immunisation, Pediatric Asthma',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 25,
                    'consultation_location': 'Paediatric Clinic, Wing B, 1st Floor, Suite 114',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Farhan Al-Mansoor',
                    'slug': 'dr-farhan-al-mansoor',
                    'department': dept_map['emergency'],
                    'specialty': spec_map['emergency-medicine'],
                    'specialty_name': 'Emergency & Trauma Care',
                    'qualification': 'MBBS, MD (Emergency Medicine), FACEM, MRCEM',
                    'experience_years': 16,
                    'bio': 'Director of Emergency Medicine and Trauma Services with international fellowship training in clinical toxicology and mass-casualty triage.',
                    'expertise': 'Cardiopulmonary Resuscitation, Acute Polytrauma, Toxicological Emergencies, Rapid Airway Management',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 20,
                    'consultation_location': 'Emergency Resuscitation Unit, Ground Floor',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Meera Sen',
                    'slug': 'dr-meera-sen',
                    'department': dept_map['cardiology'],
                    'specialty': spec_map['cardiology'],
                    'specialty_name': 'Cardiology & Vascular Medicine',
                    'qualification': 'MBBS, MD (Medicine), DM (Cardiology)',
                    'experience_years': 13,
                    'bio': 'Consultant Cardiologist specializing in echocardiography, heart failure management, and preventive clinical cardiology.',
                    'expertise': 'Stress Echocardiography, Congestive Heart Failure, Valvular Heart Disease, Preventive Cardiology',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 30,
                    'consultation_location': 'Cardiology OPD, Wing B, 2nd Floor, Suite 206',
                    'is_active': True,
                },
                {
                    'name': 'Dr. Vikramaditya Rathore',
                    'slug': 'dr-vikramaditya-rathore',
                    'department': dept_map['neurology'],
                    'specialty': spec_map['neurology'],
                    'specialty_name': 'Neurology & Neuro-Rehabilitation',
                    'qualification': 'MBBS, MD (Medicine), DM (Neurology)',
                    'experience_years': 11,
                    'bio': 'Consultant Neurologist with clinical focus on neuro-rehabilitation, movement disorders, and neuro-cognitive assessments.',
                    'expertise': 'Parkinsonism, Tremor Analysis, Neurological Gait Disorders, Cognitive Impairment Evaluation',
                    'consultation_type': 'In-person Consultation',
                    'consultation_duration_minutes': 30,
                    'consultation_location': 'Neurology OPD, Wing A, 3rd Floor, Suite 305',
                    'is_active': True,
                },
            ]

            seeded_doctors = []
            for doc_info in doctors_data:
                slug = doc_info['slug']
                doc, created = Doctor.objects.get_or_create(
                    slug=slug,
                    defaults=doc_info
                )
                if not created and doc_info.get('user') and not doc.user:
                    doc.user = doc_info['user']
                    doc.save(update_fields=['user'])
                seeded_doctors.append(doc)

            self.stdout.write(f"Doctors seeded: {len(seeded_doctors)}")

            # 5. Weekly Doctor Schedules
            days = [
                DoctorSchedule.DayOfWeek.MONDAY,
                DoctorSchedule.DayOfWeek.TUESDAY,
                DoctorSchedule.DayOfWeek.WEDNESDAY,
                DoctorSchedule.DayOfWeek.THURSDAY,
                DoctorSchedule.DayOfWeek.FRIDAY,
            ]

            total_schedules = 0
            for doctor in seeded_doctors:
                for day in days:
                    schedule, s_created = DoctorSchedule.objects.get_or_create(
                        doctor=doctor,
                        day_of_week=day,
                        defaults={
                            'start_time': datetime.time(9, 0),
                            'end_time': datetime.time(13, 0),
                            'slot_duration_minutes': doctor.consultation_duration_minutes,
                            'capacity': 1,
                            'timezone': 'Asia/Kolkata',
                            'is_working_day': True,
                            'is_active': True,
                        }
                    )
                    total_schedules += 1
                    # Ensure clinical break exists
                    ScheduleBreak.objects.get_or_create(
                        schedule=schedule,
                        start_time=datetime.time(13, 0),
                        end_time=datetime.time(14, 0),
                        defaults={'name': 'Clinical Lunch & Ward Round'}
                    )

            self.stdout.write(f"Doctor schedules verified: {total_schedules}")

        self.stdout.write(self.style.SUCCESS("All hospital clinical data seeded successfully into PostgreSQL!"))
