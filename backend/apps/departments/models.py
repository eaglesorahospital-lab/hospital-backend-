from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class Department(models.Model):
    """
    Clinical department representing a specialized hospital division or wing.
    """
    name = models.CharField(_('department name'), max_length=200, unique=True)
    slug = models.SlugField(_('url slug'), max_length=200, unique=True, db_index=True)
    specialty = models.CharField(
        _('clinical specialty domain'),
        max_length=150,
        help_text=_('Specialty field, e.g. Cardiovascular Care, Neurosciences'),
    )
    short_description = models.CharField(_('short summary'), max_length=300)
    full_description = models.TextField(_('detailed description'))
    opd_hours = models.CharField(
        _('OPD operational hours'),
        max_length=150,
        default='Mon - Sat: 09:00 AM - 04:00 PM',
    )
    location = models.CharField(
        _('facility location'),
        max_length=200,
        help_text=_('Wing, floor, and suite location in the hospital'),
    )
    contact_phone = models.CharField(_('contact phone'), max_length=50, blank=True)
    contact_email = models.EmailField(_('department email'), blank=True)
    extension = models.CharField(_('internal extension'), max_length=20, blank=True)
    image = models.ImageField(
        _('department photograph'),
        upload_to='departments/',
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
    def image_url(self):
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
        verbose_name = _('department')
        verbose_name_plural = _('departments')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DepartmentService(models.Model):
    """
    Specific clinical diagnostic or treatment service offered by a department.
    """
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='services',
    )
    name = models.CharField(_('service name'), max_length=200)
    description = models.TextField(_('service description'), blank=True)
    order = models.PositiveIntegerField(_('display order'), default=0)
    is_active = models.BooleanField(_('active status'), default=True)

    class Meta:
        verbose_name = _('department service')
        verbose_name_plural = _('department services')
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.department.name})"


class DepartmentFAQ(models.Model):
    """
    Specialty-specific patient preparation and diagnostic FAQs.
    """
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='faqs',
    )
    question = models.CharField(_('question'), max_length=300)
    answer = models.TextField(_('answer'))
    order = models.PositiveIntegerField(_('display order'), default=0)
    is_active = models.BooleanField(_('active status'), default=True)

    class Meta:
        verbose_name = _('department FAQ')
        verbose_name_plural = _('department FAQs')
        ordering = ['order', 'id']

    def __str__(self):
        return self.question
