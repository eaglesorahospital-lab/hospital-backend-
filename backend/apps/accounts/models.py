import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class UserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    for authentication instead of usernames.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('An email address is required.'))
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.SUPER_ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Hospital Platform User Model supporting role-based operations:
    SUPER_ADMIN, HOSPITAL_ADMIN, DOCTOR_STAFF, and PATIENT.
    """
    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', _('Super Admin')
        HOSPITAL_ADMIN = 'HOSPITAL_ADMIN', _('Hospital Admin')
        DOCTOR_STAFF = 'DOCTOR_STAFF', _('Doctor / Medical Staff')
        PATIENT = 'PATIENT', _('Patient')

    email = models.EmailField(_('email address'), unique=True, db_index=True)
    username = models.CharField(_('username'), max_length=150, unique=True, blank=True)
    phone = models.CharField(_('phone number'), max_length=20, blank=True)
    role = models.CharField(
        _('user role'),
        max_length=20,
        choices=Role.choices,
        default=Role.PATIENT,
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email or str(uuid.uuid4())
        super().save(*args, **kwargs)

    def __str__(self):
        full_name = self.get_full_name().strip()
        return f"{full_name} ({self.email}) - {self.get_role_display()}" if full_name else f"{self.email} - {self.get_role_display()}"


class PatientProfile(models.Model):
    """
    Patient demographics and outpatient identification profile.
    Linked to User for online portal access, but maintains independent MRN.
    """
    class Gender(models.TextChoices):
        MALE = 'MALE', _('Male')
        FEMALE = 'FEMALE', _('Female')
        OTHER = 'OTHER', _('Other')

    class BloodGroup(models.TextChoices):
        A_POS = 'A+', _('A+')
        A_NEG = 'A-', _('A-')
        B_POS = 'B+', _('B+')
        B_NEG = 'B-', _('B-')
        O_POS = 'O+', _('O+')
        O_NEG = 'O-', _('O-')
        AB_POS = 'AB+', _('AB+')
        AB_NEG = 'AB-', _('AB-')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_profile',
        null=True,
        blank=True,
        help_text=_('Associated user portal account if registered.'),
    )
    mrn = models.CharField(
        _('medical record number'),
        max_length=32,
        unique=True,
        db_index=True,
        help_text=_('Unique hospital identification code, e.g. MRN-2026-4401'),
    )
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    date_of_birth = models.DateField(_('date of birth'), null=True, blank=True)
    gender = models.CharField(
        _('gender'),
        max_length=10,
        choices=Gender.choices,
        default=Gender.MALE,
    )
    phone = models.CharField(_('phone number'), max_length=20, blank=True, db_index=True)
    email = models.EmailField(_('email address'), blank=True)
    blood_group = models.CharField(
        _('blood group'),
        max_length=5,
        choices=BloodGroup.choices,
        blank=True,
    )
    emergency_contact = models.CharField(_('emergency contact'), max_length=255, blank=True)
    address = models.TextField(_('residential address'), blank=True)
    is_active = models.BooleanField(_('active status'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('patient profile')
        verbose_name_plural = _('patient profiles')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.mrn:
            self.mrn = f"MRN-{uuid.uuid4().hex[:8].upper()}"
        if self.user:
            if not self.first_name:
                self.first_name = self.user.first_name
            if not self.last_name:
                self.last_name = self.user.last_name
            if not self.email:
                self.email = self.user.email
            if not self.phone and self.user.phone:
                self.phone = self.user.phone
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        if not name and self.user:
            name = self.user.get_full_name().strip()
        return name or self.mrn

    def __str__(self):
        return f"{self.full_name} ({self.mrn})"
