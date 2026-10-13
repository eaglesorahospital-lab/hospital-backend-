from rest_framework import serializers
from .models import HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ


class HospitalProfileSerializer(serializers.ModelSerializer):
    """
    Hospital institutional governance and contact profile serializer.
    """
    logo_url = serializers.SerializerMethodField()
    logo_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = HospitalProfile
        fields = [
            'id',
            'name',
            'legal_name',
            'tagline',
            'overview',
            'contact_phone',
            'emergency_phone',
            'contact_email',
            'address',
            'visiting_hours',
            'emergency_info',
            'logo',
            'logo_url',
            'logo_public_id',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'logo_url', 'logo_public_id', 'created_at', 'updated_at']

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        val = str(obj.logo)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return obj.logo.url
        except Exception:
            return val


class HospitalFacilitySerializer(serializers.ModelSerializer):
    """
    Hospital clinical infrastructure and amenities serializer.
    """
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = HospitalFacility
        fields = [
            'id',
            'name',
            'description',
            'image',
            'image_url',
            'image_public_id',
            'order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'image_url', 'image_public_id', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        val = str(obj.image)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return obj.image.url
        except Exception:
            return val


class HospitalAnnouncementSerializer(serializers.ModelSerializer):
    """
    Public health announcements, clinic advisories, and hospital news serializer.
    """
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = HospitalAnnouncement
        fields = [
            'id',
            'title',
            'slug',
            'category',
            'summary',
            'content',
            'image',
            'image_url',
            'image_public_id',
            'is_published',
            'published_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'image_url', 'image_public_id', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        val = str(obj.image)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return obj.image.url
        except Exception:
            return val


class HospitalFAQSerializer(serializers.ModelSerializer):
    """
    General hospital patient guidance FAQ serializer.
    """
    class Meta:
        model = HospitalFAQ
        fields = [
            'id',
            'question',
            'answer',
            'order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
