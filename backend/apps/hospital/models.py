from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class HospitalProfile(models.Model):
    """
    Institution-wide profile, legal metadata, and emergency governance.
    """
    name = models.CharField(_('hospital name'), max_length=200, default='EgleSora Hospital')
    legal_name = models.CharField(
        _('legal entity name'),
        max_length=255,
        default='EgleSora Memorial Hospital & Research Institute',
    )
    tagline = models.CharField(
        _('tagline'),
        max_length=255,
        default='Excellence in Clinical Care & Patient Safety',
    )
    overview = models.TextField(
        _('institutional overview'),
        help_text=_('Core mission, clinical governance, and tertiary healthcare scope.'),
    )
    contact_phone = models.CharField(_('general phone'), max_length=50, default='+91 (0) 22 0000 2222')
    emergency_phone = models.CharField(_('emergency hotline'), max_length=50, default='+91 (0) 22 0000 1111')
    contact_email = models.EmailField(_('general inquiry email'), default='desk@eglesorahospital.org')
    address = models.TextField(_('physical address'), default='12 Medical District Avenue, City Center')
    visiting_hours = models.CharField(
        _('visiting hours'),
        max_length=255,
        default='Monday - Saturday: 08:00 AM - 08:00 PM',
    )
    emergency_info = models.TextField(
        _('emergency services protocol'),
        help_text=_('24/7 Acute trauma triage protocols and ambulance bay directions.'),
    )
    logo = models.ImageField(
        _('hospital logo/emblem'),
        upload_to='hospital/',
        null=True,
        blank=True,
        help_text=_('Media storage logo compatible with Cloudinary.'),
    )
    logo_public_id = models.CharField(
        _('cloudinary public id'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Cloudinary asset public ID for secure deletion and replacement.'),
    )
    is_active = models.BooleanField(_('active profile'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def logo_url(self):
        if not self.logo:
            return None
        val = str(self.logo)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return self.logo.url
        except Exception:
            return val

    class Meta:
        verbose_name = _('hospital profile')
        verbose_name_plural = _('hospital profile')

    def __str__(self):
        return self.name


class HospitalFacility(models.Model):
    """
    Hospital clinical infrastructure and medical wings.
    """
    name = models.CharField(_('facility name'), max_length=200)
    description = models.TextField(_('facility description'))
    image = models.ImageField(
        _('facility photograph'),
        upload_to='facilities/',
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
    order = models.PositiveIntegerField(_('display order'), default=0)
    is_active = models.BooleanField(_('active status'), default=True)
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
        verbose_name = _('hospital facility')
        verbose_name_plural = _('hospital facilities')
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class HospitalAnnouncement(models.Model):
    """
    Public health announcements, clinic advisories, and hospital news.
    """
    title = models.CharField(_('headline'), max_length=255)
    slug = models.SlugField(_('url slug'), max_length=255, unique=True)
    category = models.CharField(_('category'), max_length=100, default='Advisory')
    summary = models.CharField(_('brief summary'), max_length=500)
    content = models.TextField(_('announcement body'))
    image = models.ImageField(
        _('announcement banner'),
        upload_to='announcements/',
        null=True,
        blank=True,
        help_text=_('Media storage banner compatible with Cloudinary.'),
    )
    image_public_id = models.CharField(
        _('cloudinary public id'),
        max_length=255,
        blank=True,
        null=True,
        help_text=_('Cloudinary asset public ID for secure deletion and replacement.'),
    )
    is_published = models.BooleanField(_('published status'), default=True, db_index=True)
    published_at = models.DateTimeField(_('publication date'), null=True, blank=True)
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
        verbose_name = _('hospital announcement')
        verbose_name_plural = _('hospital announcements')
        ordering = ['-published_at', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class HospitalFAQ(models.Model):
    """
    General institutional and patient guidance FAQs.
    """
    question = models.CharField(_('question'), max_length=300)
    answer = models.TextField(_('answer'))
    order = models.PositiveIntegerField(_('display order'), default=0)
    is_active = models.BooleanField(_('active status'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('hospital FAQ')
        verbose_name_plural = _('hospital FAQs')
        ordering = ['order', 'id']

    def __str__(self):
        return self.question
