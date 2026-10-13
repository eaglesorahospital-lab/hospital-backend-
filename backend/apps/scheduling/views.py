from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import DoctorSchedule, DoctorLeave, ScheduleOverride
from .serializers import (
    DoctorScheduleSerializer,
    DoctorLeaveSerializer,
    ScheduleOverrideSerializer,
)
from config.pagination import StandardResultsSetPagination
from apps.accounts.permissions import IsStaffOrAdmin, IsAdminUserOrReadOnly
from apps.doctors.models import Doctor
from .services import AvailabilityEngine


class DoctorScheduleViewSet(viewsets.ModelViewSet):
    """
    Weekly doctor shift allocations API.
    Public read-only; shift modifications require staff or administrative privileges.
    """
    queryset = DoctorSchedule.objects.all().select_related('doctor').prefetch_related('breaks')
    serializer_class = DoctorScheduleSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['doctor', 'doctor__slug', 'day_of_week', 'is_working_day', 'is_active']
    search_fields = ['doctor__name', 'day_of_week']
    ordering_fields = ['day_of_week', 'start_time']
    ordering = ['doctor', 'day_of_week']

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='availability')
    def availability(self, request):
        doctor_id = request.query_params.get('doctor')
        doctor_slug = request.query_params.get('doctor__slug') or request.query_params.get('slug')
        date_str = request.query_params.get('date')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not date_str and not start_date_str:
            return Response(
                {"detail": "Query parameter 'date' (YYYY-MM-DD) or 'start_date' (YYYY-MM-DD) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        doctor = None
        if doctor_id:
            if str(doctor_id).isdigit():
                doctor = Doctor.objects.filter(id=int(doctor_id)).first()
            else:
                doctor = Doctor.objects.filter(slug=doctor_id).first()
        if not doctor and doctor_slug:
            doctor = Doctor.objects.filter(slug=doctor_slug).first()

        if not doctor:
            return Response(
                {"detail": "A valid doctor parameter ('doctor' ID or 'doctor__slug') is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date_str:
            data = AvailabilityEngine.get_doctor_availability_range(
                doctor, start_date_str, end_date_str or start_date_str
            )
        else:
            data = AvailabilityEngine.get_doctor_availability(doctor, date_str)
        return Response(data, status=status.HTTP_200_OK)


class DoctorLeaveViewSet(viewsets.ModelViewSet):
    """
    Doctor leave allocations API.
    Public read-only; leave modifications require staff or administrative privileges.
    """
    queryset = DoctorLeave.objects.all().select_related('doctor')
    serializer_class = DoctorLeaveSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['doctor', 'doctor__slug', 'is_active']
    search_fields = ['doctor__name', 'reason']
    ordering_fields = ['start_date', 'end_date']
    ordering = ['start_date']


class ScheduleOverrideViewSet(viewsets.ModelViewSet):
    """
    Doctor schedule overrides API.
    Public read-only; override modifications require staff or administrative privileges.
    """
    queryset = ScheduleOverride.objects.all().select_related('doctor')
    serializer_class = ScheduleOverrideSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['doctor', 'doctor__slug', 'override_date', 'override_type', 'is_available']
    search_fields = ['doctor__name', 'reason']
    ordering_fields = ['override_date', 'created_at']
    ordering = ['override_date']
