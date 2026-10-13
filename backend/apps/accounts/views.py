from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import PatientProfile, User
from .serializers import PatientProfileSerializer, PatientProfileCreateUpdateSerializer
from .permissions import IsPatientOwnerOrStaff
from config.pagination import StandardResultsSetPagination


class PatientProfileViewSet(viewsets.ModelViewSet):
    """
    Outpatient demographics API.
    Protected by RBAC:
    - Patients can only view and update their own demographic record.
    - Medical staff and administrators can access all patient records.
    - Anonymous requests are rejected (401).
    """
    permission_classes = [permissions.IsAuthenticated, IsPatientOwnerOrStaff]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['gender', 'blood_group', 'is_active']
    search_fields = ['mrn', 'first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['created_at', 'last_name', 'first_name', 'date_of_birth']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return PatientProfile.objects.none()

        # Admins and medical staff have organization-wide visibility
        if (
            user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
            or user.is_staff
            or user.is_superuser
        ):
            return PatientProfile.objects.all().select_related('user')

        # Patients are restricted strictly to their own demographic record
        return PatientProfile.objects.filter(user=user).select_related('user')

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PatientProfileCreateUpdateSerializer
        return PatientProfileSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == User.Role.PATIENT:
            if hasattr(user, 'patient_profile') and user.patient_profile:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": "Patient profile already exists for this account."})
            serializer.save(user=user)
        else:
            serializer.save()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        Retrieve or update the authenticated patient's own profile.
        Strictly derives identity from the validated authentication context (request.user).
        """
        user = request.user
        if not (user and user.is_authenticated):
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        profile = getattr(user, 'patient_profile', None)
        if not profile and user.role == User.Role.PATIENT:
            # Check if an existing unlinked profile matches the user's email
            if user.email:
                profile = PatientProfile.objects.filter(email__iexact=user.email, user__isnull=True).first()
                if profile:
                    profile.user = user
                    profile.save(update_fields=['user'])

        if request.method == 'GET':
            if not profile:
                return Response(
                    {"detail": "No patient profile associated with this account.", "profile": None},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = PatientProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif request.method in ['PUT', 'PATCH']:
            if not profile:
                # First-time profile initialization for authenticated user
                data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
                serializer = PatientProfileCreateUpdateSerializer(data=data, partial=True)
                serializer.is_valid(raise_exception=True)
                profile = serializer.save(user=user)
                return Response(PatientProfileSerializer(profile).data, status=status.HTTP_201_CREATED)
            else:
                serializer = PatientProfileCreateUpdateSerializer(profile, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                profile = serializer.save()
                return Response(PatientProfileSerializer(profile).data, status=status.HTTP_200_OK)

