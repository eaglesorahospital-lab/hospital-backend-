from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Specialty, Doctor
from .serializers import (
    SpecialtySerializer,
    DoctorListSerializer,
    DoctorDetailSerializer,
)
from config.pagination import StandardResultsSetPagination
from config.media_service import MediaService, CLOUDINARY_FOLDERS
from config.throttling import MediaUploadRateThrottle
from apps.accounts.permissions import IsAdminUserOrReadOnly, CanManageDoctorMedia
from apps.scheduling.services import AvailabilityEngine


class SpecialtyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Medical clinical specialties directory API.
    Public read-only; administrative mutations.
    """
    queryset = Specialty.objects.filter(is_active=True)
    serializer_class = SpecialtySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_field = 'slug'
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class DoctorViewSet(viewsets.ModelViewSet):
    """
    Consultant doctor directory API.
    Supports filtering by department, specialty, consultation type, and full-text search.
    Public read-only; administrative mutations and media upload actions protected by RBAC.
    """
    queryset = Doctor.objects.all().select_related('department', 'specialty')
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_field = 'slug'
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'department',
        'department__slug',
        'specialty',
        'specialty__slug',
        'consultation_type',
        'is_active',
    ]
    search_fields = ['name', 'qualification', 'expertise', 'specialty_name', 'department__name']
    ordering_fields = ['name', 'experience_years', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        user = self.request.user
        qs = Doctor.objects.all().select_related('department', 'specialty')
        # Public anonymous users and non-staff patients should only see active doctors
        if not (user and user.is_authenticated and (user.is_staff or getattr(user, 'role', None) in ['SUPER_ADMIN', 'HOSPITAL_ADMIN', 'DOCTOR_STAFF'])):
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in ['upload_photo', 'delete_photo']:
            return [CanManageDoctorMedia()]
        if self.action in ['update', 'partial_update']:
            return [CanManageDoctorMedia()]
        return super().get_permissions()

    def get_object(self):
        """
        Supports lookup both by string slug and by integer ID.
        """
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_val = self.kwargs.get(lookup_url_kwarg)
        qs = self.get_queryset()
        if lookup_val and str(lookup_val).isdigit():
            obj = qs.filter(id=int(lookup_val)).first()
            if obj:
                self.check_object_permissions(self.request, obj)
                return obj
        return super().get_object()

    def get_serializer_class(self):
        if self.action in ['retrieve', 'update', 'partial_update', 'create']:
            return DoctorDetailSerializer
        return DoctorListSerializer

    def perform_update(self, serializer):
        # If multipart image file uploaded directly via PATCH/PUT
        image_file = self.request.FILES.get('image') or self.request.FILES.get('photo')
        if image_file:
            doctor = serializer.instance
            upload_res = MediaService.replace_model_image(
                instance=doctor,
                file_obj=image_file,
                image_field_name='image',
                public_id_field_name='image_public_id',
                folder=CLOUDINARY_FOLDERS['doctors'],
            )
            serializer.save(image=upload_res['url'], image_public_id=upload_res['public_id'])
        else:
            serializer.save()

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[CanManageDoctorMedia],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MediaUploadRateThrottle],
        url_path='upload-photo'
    )
    def upload_photo(self, request, slug=None):
        """
        Secure doctor profile photo upload/replacement endpoint.
        Authorized for Super Admin, Hospital Admin, or the specific Doctor staff owner.
        """
        doctor = self.get_object()
        file_obj = request.FILES.get('image') or request.FILES.get('photo') or request.FILES.get('file')
        if not file_obj:
            return Response(
                {"detail": "No image file provided in request. Expected multipart field 'image' or 'photo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = MediaService.replace_model_image(
            instance=doctor,
            file_obj=file_obj,
            image_field_name='image',
            public_id_field_name='image_public_id',
            folder=CLOUDINARY_FOLDERS['doctors'],
        )
        doctor.refresh_from_db()
        serializer = DoctorDetailSerializer(doctor, context={'request': request})
        return Response({
            "message": "Doctor photo uploaded successfully.",
            "doctor_id": doctor.id,
            "photo_url": result['url'],
            "public_id": result['public_id'],
            "doctor": serializer.data,
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['delete'],
        permission_classes=[CanManageDoctorMedia],
        url_path='delete-photo'
    )
    def delete_photo(self, request, slug=None):
        """
        Secure doctor profile photo deletion endpoint.
        Clears database reference and destroys Cloudinary asset.
        """
        doctor = self.get_object()
        MediaService.delete_model_image(
            instance=doctor,
            image_field_name='image',
            public_id_field_name='image_public_id',
        )
        doctor.refresh_from_db()
        serializer = DoctorDetailSerializer(doctor, context={'request': request})
        return Response({
            "message": "Doctor photo removed successfully.",
            "doctor_id": doctor.id,
            "photo_url": None,
            "doctor": serializer.data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], url_path='availability')
    def availability(self, request, slug=None):
        doctor = self.get_object()
        date_str = request.query_params.get('date')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not date_str and not start_date_str:
            return Response(
                {"detail": "Query parameter 'date' (YYYY-MM-DD) or 'start_date' (YYYY-MM-DD) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if start_date_str:
            data = AvailabilityEngine.get_doctor_availability_range(
                doctor, start_date_str, end_date_str or start_date_str
            )
        else:
            data = AvailabilityEngine.get_doctor_availability(doctor, date_str)
        return Response(data, status=status.HTTP_200_OK)

