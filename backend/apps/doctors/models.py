from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.conf import settings


class Specialty(models.Model):
    """
    Medical specialty categorization (e.g. Cardiology, Neurology, Orthopedics).
    """
    name = models.CharField(_('specialty name'), max_length=150, unique=True)
    slug = models.SlugField(_('url slug'), max_length=150, unique=True, db_index=True)
    description = models.TextField(_('description'), blank=True)
    is_active = models.BooleanField(_('active status'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('specialty')
        verbose_name_plural = _('specialties')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Doctor(models.Model):
    """
    Doctor / Consultant profile with clinical qualifications, departmental privileges,
    and consultation parameters.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='doctor_profile',
        null=True,
        blank=True,
        help_text=_('Associated staff user account for platform login.'),
    )
    name = models.CharField(_('full name with title'), max_length=200)
    slug = models.SlugField(_('url slug'), max_length=200, unique=True, db_index=True)
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.PROTECT,
        related_name='doctors',
        help_text=_('Primary clinical department.'),
    )
    specialty = models.ForeignKey(
        Specialty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='doctors',
        help_text=_('Primary clinical specialty area.'),
    )
    specialty_name = models.CharField(
        _('specialty display text'),
        max_length=150,
        blank=True,
        help_text=_('Denormalized or custom specialty label, e.g. Cardiology.'),
    )
    qualification = models.CharField(
        _('academic qualifications'),
        max_length=300,
        help_text=_('e.g. MBBS, MD (General Medicine), DM (Cardiology)'),
    )
    experience_years = models.PositiveIntegerField(
        _('years of hospital experience'),
        default=5,
    )
    bio = models.TextField(_('professional biography'))
    expertise = models.TextField(
        _('clinical areas of expertise'),
        blank=True,
        help_text=_('Comma-separated or multiline list of core clinical proficiencies.'),
    )
    consultation_type = models.CharField(
        _('consultation modality'),
        max_length=100,
        default='In-person Consultation',
    )
    consultation_duration_minutes = models.PositiveIntegerField(
        _('standard slot duration (minutes)'),
        default=30,
    )
    consultation_location = models.CharField(
        _('OPD suite / consulting room location'),
        max_length=200,
        help_text=_('e.g. Cardiology OPD, Wing B, 2nd Floor, Suite 204'),
    )
    image = models.ImageField(
        _('profile photograph'),
        upload_to='doctors/',
        null=True,
        blank=True,
        help_text=_('Media storage image compatible with Cloudinary.'),
    )
    image_public_id = models.CharField(
        _('cloudinary public id'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Cloudinary asset public ID for secure deletion and replacement.'),
    )
    is_active = models.BooleanField(_('active status'), default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def photo_url(self):
        if not self.image:
            return None
        val = str(self.image)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return self.image.url
        except Exception:
            return val

    class Meta:
        verbose_name = _('doctor')
        verbose_name_plural = _('doctors')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.specialty and not self.specialty_name:
            self.specialty_name = self.specialty.name
        super().save(*args, **kwargs)

    def __str__(self):
        dept_str = f" - {self.department.name}" if self.department else ""
        return f"{self.name} ({self.specialty_name or 'General'}){dept_str}"
