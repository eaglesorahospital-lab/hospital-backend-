"""
Management command to securely provision initial Hospital Administrator and Doctor Staff accounts.
Conforms strictly to Django password hashing, role permissions, and idempotency standards.
"""

import os
import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Idempotently creates initial hospital administrator and doctor staff accounts "
        "using secure Django password hashing and environment variables or interactive prompt."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-email',
            type=str,
            default=os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@eglesorahospital.org'),
            help='Email address for the initial Hospital Administrator.',
        )
        parser.add_argument(
            '--admin-first-name',
            type=str,
            default='Hospital',
            help='First name for the administrator.',
        )
        parser.add_argument(
            '--admin-last-name',
            type=str,
            default='Administrator',
            help='Last name for the administrator.',
        )
        parser.add_argument(
            '--doctor-email',
            type=str,
            default=os.environ.get('INITIAL_DOCTOR_EMAIL', 'doctor.varma@eglesorahospital.org'),
            help='Email address for the initial Doctor / Medical Staff member.',
        )
        parser.add_argument(
            '--doctor-first-name',
            type=str,
            default='Rajesh',
            help='First name for the doctor.',
        )
        parser.add_argument(
            '--doctor-last-name',
            type=str,
            default='Varma',
            help='Last name for the doctor.',
        )
        parser.add_argument(
            '--interactive',
            action='store_true',
            help='Interactively prompt for passwords using masked console input (getpass).',
        )
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Reset password for existing staff accounts if password is provided via environment or interactive prompt.',
        )

    def handle(self, *args, **options):
        admin_email = options['admin_email'].strip().lower()
        admin_first = options['admin_first_name'].strip()
        admin_last = options['admin_last_name'].strip()

        doctor_email = options['doctor_email'].strip().lower()
        doctor_first = options['doctor_first_name'].strip()
        doctor_last = options['doctor_last_name'].strip()

        is_interactive = options['interactive']
        reset_passwords = options['reset_passwords'] or bool(os.environ.get('RESET_STAFF_PASSWORDS'))

        self.stdout.write(self.style.NOTICE("=== Eagle Sora Hospital: Staff Account Provisioning ==="))

        with transaction.atomic():
            # 1. Provision Administrator Account
            admin_user = User.objects.filter(email=admin_email).first()
            admin_password = os.environ.get('INITIAL_ADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD')
            if admin_user:
                if reset_passwords:
                    if is_interactive and not admin_password:
                        admin_password = getpass.getpass(f"Enter new secure password for Administrator ({admin_email}): ")
                        admin_password_confirm = getpass.getpass("Confirm password: ")
                        if admin_password != admin_password_confirm:
                            raise CommandError("Administrator passwords do not match.")

                    if not admin_password or len(admin_password) < 8:
                        raise CommandError(
                            "Administrator password must be at least 8 characters. "
                            "Set INITIAL_ADMIN_PASSWORD or ADMIN_PASSWORD environment variable or use --interactive."
                        )

                    admin_user.set_password(admin_password)
                    admin_user.role = User.Role.HOSPITAL_ADMIN
                    admin_user.is_staff = True
                    admin_user.is_active = True
                    admin_user.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[RESET] Reset password and verified role for existing administrator '{admin_email}' (Role: {admin_user.role})."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[EXISTS] Administrator account '{admin_email}' already exists (Role: {admin_user.role}). "
                            "Preserving existing credentials and permissions (use --reset-passwords to update)."
                        )
                    )
            else:
                if is_interactive and not admin_password:
                    admin_password = getpass.getpass(f"Enter secure password for Administrator ({admin_email}): ")
                    admin_password_confirm = getpass.getpass("Confirm password: ")
                    if admin_password != admin_password_confirm:
                        raise CommandError("Administrator passwords do not match.")

                if not admin_password or len(admin_password) < 8:
                    raise CommandError(
                        "Administrator password must be at least 8 characters. "
                        "Set INITIAL_ADMIN_PASSWORD environment variable or use --interactive."
                    )

                admin_user = User.objects.create_user(
                    email=admin_email,
                    password=admin_password,
                    first_name=admin_first,
                    last_name=admin_last,
                    role=User.Role.HOSPITAL_ADMIN,
                    is_staff=True,
                    is_active=True,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[CREATED] Administrator account created: {admin_email} (Role: {admin_user.role})"
                    )
                )

            # 1b. Idempotently configure Django Admin model permissions for Hospital Administrator
            from django.contrib.auth.models import Group, Permission
            admin_group, _ = Group.objects.get_or_create(name='Hospital Administrators')
            hospital_apps = ['hospital', 'departments', 'doctors', 'scheduling', 'appointments', 'notifications', 'accounts']
            hospital_perms = Permission.objects.filter(content_type__app_label__in=hospital_apps)
            admin_group.permissions.set(hospital_perms)
            admin_user.groups.add(admin_group)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[PERMISSIONS] Configured 'Hospital Administrators' group ({hospital_perms.count()} permissions) for {admin_email}."
                )
            )

            # 2. Provision Doctor / Medical Staff Account
            doctor_user = User.objects.filter(email=doctor_email).first()
            doctor_password = os.environ.get('INITIAL_DOCTOR_PASSWORD') or os.environ.get('DOCTOR_PASSWORD')
            if doctor_user:
                if reset_passwords and doctor_password:
                    if len(doctor_password) < 8:
                        raise CommandError("Doctor password must be at least 8 characters.")
                    doctor_user.set_password(doctor_password)
                    doctor_user.role = User.Role.DOCTOR_STAFF
                    doctor_user.is_staff = True
                    doctor_user.is_active = True
                    doctor_user.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[RESET] Reset password and verified role for existing doctor '{doctor_email}' (Role: {doctor_user.role})."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[EXISTS] Doctor account '{doctor_email}' already exists (Role: {doctor_user.role}). "
                            "Preserving existing credentials and permissions (use --reset-passwords to update)."
                        )
                    )
            else:
                if is_interactive and not doctor_password:
                    doctor_password = getpass.getpass(f"Enter secure password for Doctor Staff ({doctor_email}): ")
                    doctor_password_confirm = getpass.getpass("Confirm password: ")
                    if doctor_password != doctor_password_confirm:
                        raise CommandError("Doctor passwords do not match.")

                if not doctor_password or len(doctor_password) < 8:
                    raise CommandError(
                        "Doctor password must be at least 8 characters. "
                        "Set INITIAL_DOCTOR_PASSWORD environment variable or use --interactive."
                    )

                doctor_user = User.objects.create_user(
                    email=doctor_email,
                    password=doctor_password,
                    first_name=doctor_first,
                    last_name=doctor_last,
                    role=User.Role.DOCTOR_STAFF,
                    is_staff=True,
                    is_active=True,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[CREATED] Doctor staff account created: {doctor_email} (Role: {doctor_user.role})"
                    )
                )

                # Try linking with existing Doctor profile if available
                try:
                    from apps.doctors.models import Doctor
                    doc_profile = Doctor.objects.filter(name__icontains=doctor_last).first()
                    if doc_profile and not doc_profile.user:
                        doc_profile.user = doctor_user
                        doc_profile.save(update_fields=['user'])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[LINKED] Linked user {doctor_email} to clinical doctor profile: {doc_profile.name}"
                            )
                        )
                except Exception as exc:
                    self.stdout.write(self.style.NOTICE(f"[NOTICE] Doctor profile auto-link skipped: {exc}"))

        self.stdout.write(self.style.SUCCESS("Staff accounts provisioning procedure completed safely."))
