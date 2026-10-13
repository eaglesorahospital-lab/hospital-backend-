from rest_framework import viewsets, permissions
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Notification, AuditLog
from .serializers import NotificationSerializer, AuditLogSerializer
from config.pagination import StandardResultsSetPagination
from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrHospitalAdmin


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Outbound communication log API.
    Protected by RBAC:
    - Patients view notifications directed to their user account.
    - Staff and administrators view organizational communication logs.
    - Anonymous requests are rejected (401).
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['notification_type', 'channel', 'status', 'appointment']
    search_fields = ['recipient', 'subject', 'message']
    ordering_fields = ['created_at', 'sent_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Notification.objects.none()

        base_qs = Notification.objects.select_related('appointment', 'recipient_user')

        if (
            user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
            or user.is_staff
            or user.is_superuser
        ):
            return base_qs

        # Patients only see notifications addressed to them
        return base_qs.filter(recipient_user=user)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    System activity audit trail API (strictly read-only).
    Protected by RBAC: Restricted exclusively to Super Admins and Hospital Admins.
    Patients and unprivileged users receive 403 Forbidden. Anonymous receives 401.
    """
    queryset = AuditLog.objects.all().select_related('actor')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminOrHospitalAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['action', 'resource_type', 'result']
    search_fields = ['actor_name', 'action', 'resource_id', 'details']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
