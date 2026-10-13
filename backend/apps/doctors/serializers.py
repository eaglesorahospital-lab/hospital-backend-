from rest_framework import serializers
from .models import Specialty, Doctor
from apps.departments.models import Department


class SpecialtySerializer(serializers.ModelSerializer):
    """
    Clinical medical specialty serializer.
    """
    class Meta:
        model = Specialty
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at']


class DoctorDepartmentSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight department serializer for doctor responses.
    """
    class Meta:
        model = Department
        fields = ['id', 'name', 'slug', 'location', 'opd_hours']


class DoctorSpecialtySummarySerializer(serializers.ModelSerializer):
    """
    Lightweight specialty serializer for doctor responses.
    """
    class Meta:
        model = Specialty
        fields = ['id', 'name', 'slug']


class DoctorListSerializer(serializers.ModelSerializer):
    """
    Doctor catalog card summary serializer for listings, search, and directory filters.
    """
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_slug = serializers.CharField(source='department.slug', read_only=True)
    photo_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            'id',
            'name',
            'slug',
            'department',
            'department_name',
            'department_slug',
            'specialty',
            'specialty_name',
            'qualification',
            'experience_years',
            'consultation_type',
            'consultation_duration_minutes',
            'consultation_location',
            'image',
            'photo_url',
            'image_url',
            'image_public_id',
            'is_active',
        ]
        read_only_fields = ['id', 'slug', 'image_public_id', 'photo_url', 'image_url']

    def get_photo_url(self, obj):
        if not obj.image:
            return None
        val = str(obj.image)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return obj.image.url
        except Exception:
            return val

    def get_image_url(self, obj):
        return self.get_photo_url(obj)


class DoctorDetailSerializer(serializers.ModelSerializer):
    """
    Detailed clinical practitioner biography, credentials, and consultation parameters.
    """
    department_detail = DoctorDepartmentSummarySerializer(source='department', read_only=True)
    specialty_detail = DoctorSpecialtySummarySerializer(source='specialty', read_only=True)
    photo_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            'id',
            'name',
            'slug',
            'department',
            'department_detail',
            'specialty',
            'specialty_detail',
            'specialty_name',
            'qualification',
            'experience_years',
            'bio',
            'expertise',
            'consultation_type',
            'consultation_duration_minutes',
            'consultation_location',
            'image',
            'photo_url',
            'image_url',
            'image_public_id',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'image_public_id', 'photo_url', 'image_url', 'created_at', 'updated_at']

    def get_photo_url(self, obj):
        if not obj.image:
            return None
        val = str(obj.image)
        if val.startswith('http://') or val.startswith('https://'):
            return val
        try:
            return obj.image.url
        except Exception:
            return val

    def get_image_url(self, obj):
        return self.get_photo_url(obj)
