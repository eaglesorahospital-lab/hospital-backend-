from rest_framework import serializers
from .models import Notification, AuditLog


class NotificationSerializer(serializers.ModelSerializer):
    """
    Outbound communication log serializer.
    """
    appointment_reference = serializers.CharField(source='appointment.reference', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'recipient',
            'recipient_user',
            'appointment',
            'appointment_reference',
            'notification_type',
            'channel',
            'status',
            'subject',
            'message',
            'provider_reference',
            'retry_count',
            'error_message',
            'idempotency_key',
            'sent_at',
            'failed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only activity audit trail serializer.
    Provides non-repudiation and activity forensics.
    """
    class Meta:
        model = AuditLog
        fields = [
            'id',
            'actor',
            'actor_name',
            'role',
            'action',
            'resource_type',
            'resource_id',
            'result',
            'details',
            'metadata',
            'ip_address',
            'timestamp',
        ]
        read_only_fields = fields
