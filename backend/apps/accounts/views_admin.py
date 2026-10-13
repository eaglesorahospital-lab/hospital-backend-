"""
Administrative Account Management API Views.
Strictly restricted to SUPER_ADMIN users for provisioning and managing
Hospital Administrator accounts and enforcing RBAC security policies.
"""

import logging
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from .models import User
from .permissions import IsSuperAdmin
from .serializers import AdministratorSerializer, AdministratorCreateSerializer
from config.pagination import StandardResultsSetPagination

logger = logging.getLogger('hospital.accounts')


class AdministratorViewSet(viewsets.ModelViewSet):
    """
    Hospital Administrator Management API.
    Strictly protected by IsSuperAdmin permission:
    - Only SUPER_ADMIN (or Django superuser) can list, create, or modify administrator accounts.
    - Regular HOSPITAL_ADMIN, DOCTOR_STAFF, and PATIENTS receive 403 Forbidden.
    - Anonymous requests receive 401 Unauthorized.
    - Enforces rules against self-deactivation and deactivating Super Administrators.
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'phone']
    ordering_fields = ['date_joined', 'last_name', 'first_name', 'email']
    ordering = ['-date_joined']

    def get_queryset(self):
        # Expose all administrative accounts (SUPER_ADMIN and HOSPITAL_ADMIN)
        return User.objects.filter(
            role__in=[User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN]
        ).order_by('-date_joined')

    def get_serializer_class(self):
        if self.action == 'create':
            return AdministratorCreateSerializer
        return AdministratorSerializer

    def create(self, request, *args, **kwargs):
        """
        Provisions a new Hospital Administrator with hashed password,
        is_staff=True, and assignment to the 'Hospital Administrators' group.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info(
            f"Super Admin {request.user.email} provisioned Hospital Administrator {user.email} (ID: {user.id})."
        )
        output_serializer = AdministratorSerializer(user, context=self.get_serializer_context())
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        instance = self.get_object()
        new_is_active = serializer.validated_data.get('is_active')

        if new_is_active is False:
            if instance == self.request.user:
                raise ValidationError({"detail": "You cannot deactivate your own administrator account."})
            if instance.role == User.Role.SUPER_ADMIN or instance.is_superuser:
                raise ValidationError({"detail": "Super Administrator accounts cannot be deactivated through this interface."})

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """
        Prevent hard deletion of administrator accounts to maintain audit integrity.
        Admins should be deactivated instead.
        """
        return Response(
            {"detail": "Administrator accounts cannot be deleted to preserve audit trails. Deactivate the account instead."},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        """
        Toggles is_active status of a Hospital Administrator account.
        Disallows deactivating self or Super Administrators.
        """
        admin_user = self.get_object()

        if admin_user == request.user:
            return Response(
                {"detail": "You cannot deactivate your own administrator account."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if admin_user.role == User.Role.SUPER_ADMIN or admin_user.is_superuser:
            return Response(
                {"detail": "Super Administrator accounts cannot be deactivated through this interface."},
                status=status.HTTP_400_BAD_REQUEST
            )

        admin_user.is_active = not admin_user.is_active
        admin_user.save(update_fields=['is_active'])

        logger.info(
            f"Super Admin {request.user.email} set active status of {admin_user.email} to {admin_user.is_active}."
        )

        return Response(
            AdministratorSerializer(admin_user, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK
        )
