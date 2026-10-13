from rest_framework import viewsets, response, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Department, DepartmentService, DepartmentFAQ
from .serializers import (
    DepartmentListSerializer,
    DepartmentDetailSerializer,
    DepartmentServiceSerializer,
    DepartmentFAQSerializer,
)
from config.pagination import StandardResultsSetPagination
from config.media_service import MediaService, CLOUDINARY_FOLDERS
from config.throttling import MediaUploadRateThrottle
from apps.accounts.permissions import IsAdminUserOrReadOnly, IsAdminOrHospitalAdmin


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    Public clinical department directory API.
    Supports list, search, retrieve by slug, nested service/FAQ actions,
    and media image upload/delete restricted by RBAC.
    """
    queryset = Department.objects.all().prefetch_related('services', 'faqs')
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_field = 'slug'
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'specialty']
    search_fields = ['name', 'specialty', 'short_description', 'full_description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DepartmentDetailSerializer
        return DepartmentListSerializer

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAdminOrHospitalAdmin],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MediaUploadRateThrottle],
        url_path='upload-image'
    )
    def upload_image(self, request, slug=None):
        dept = self.get_object()
        file_obj = request.FILES.get('image') or request.FILES.get('file')
        if not file_obj:
            return response.Response(
                {"detail": "No image file provided. Expected multipart field 'image'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        res = MediaService.replace_model_image(
            instance=dept,
            file_obj=file_obj,
            image_field_name='image',
            public_id_field_name='image_public_id',
            folder=CLOUDINARY_FOLDERS['departments'],
        )
        dept.refresh_from_db()
        return response.Response({
            "message": "Department image uploaded successfully.",
            "department_id": dept.id,
            "image_url": res['url'],
            "public_id": res['public_id'],
            "department": DepartmentDetailSerializer(dept, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['delete'],
        permission_classes=[IsAdminOrHospitalAdmin],
        url_path='delete-image'
    )
    def delete_image(self, request, slug=None):
        dept = self.get_object()
        MediaService.delete_model_image(
            instance=dept,
            image_field_name='image',
            public_id_field_name='image_public_id',
        )
        dept.refresh_from_db()
        return response.Response({
            "message": "Department image removed successfully.",
            "department_id": dept.id,
            "image_url": None,
            "department": DepartmentDetailSerializer(dept, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def services(self, request, slug=None):
        """Returns the list of active services for this department."""
        dept = self.get_object()
        services = dept.services.filter(is_active=True).order_by('order', 'name')
        serializer = DepartmentServiceSerializer(services, many=True)
        return response.Response(serializer.data)

    @action(detail=True, methods=['get'])
    def faqs(self, request, slug=None):
        """Returns the list of active FAQs for this department."""
        dept = self.get_object()
        faqs = dept.faqs.filter(is_active=True).order_by('order', 'id')
        serializer = DepartmentFAQSerializer(faqs, many=True)
        return response.Response(serializer.data)
