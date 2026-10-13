from rest_framework import serializers
from .models import Department, DepartmentService, DepartmentFAQ


class DepartmentServiceSerializer(serializers.ModelSerializer):
    """
    Departmental clinical service / procedure serializer.
    """
    class Meta:
        model = DepartmentService
        fields = [
            'id',
            'department',
            'name',
            'description',
            'order',
            'is_active',
        ]
        read_only_fields = ['id']


class DepartmentFAQSerializer(serializers.ModelSerializer):
    """
    Departmental clinical FAQ serializer.
    """
    class Meta:
        model = DepartmentFAQ
        fields = [
            'id',
            'department',
            'question',
            'answer',
            'order',
            'is_active',
        ]
        read_only_fields = ['id']


class DepartmentListSerializer(serializers.ModelSerializer):
    """
    Department catalog summary serializer for public directory listing.
    """
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'slug',
            'specialty',
            'short_description',
            'opd_hours',
            'location',
            'contact_phone',
            'contact_email',
            'extension',
            'image',
            'image_url',
            'image_public_id',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'slug', 'image_url', 'image_public_id', 'created_at']

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


class DepartmentDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive department detail serializer with embedded services and FAQs.
    """
    services = DepartmentServiceSerializer(many=True, read_only=True)
    faqs = DepartmentFAQSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    image_public_id = serializers.CharField(read_only=True)

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'slug',
            'specialty',
            'short_description',
            'full_description',
            'opd_hours',
            'location',
            'contact_phone',
            'contact_email',
            'extension',
            'image',
            'image_url',
            'image_public_id',
            'is_active',
            'services',
            'faqs',
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
