from rest_framework import viewsets, response, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ
from .serializers import (
    HospitalProfileSerializer,
    HospitalFacilitySerializer,
    HospitalAnnouncementSerializer,
    HospitalFAQSerializer,
)
from config.pagination import StandardResultsSetPagination
from config.media_service import MediaService, CLOUDINARY_FOLDERS
from config.throttling import MediaUploadRateThrottle
from apps.accounts.permissions import IsAdminUserOrReadOnly, IsAdminOrHospitalAdmin


class HospitalProfileViewSet(viewsets.ModelViewSet):
    """
    Hospital profile API.
    Provides institutional profile data and emergency contact channels.
    Media logo management restricted to Hospital Admins & Super Admins.
    """
    queryset = HospitalProfile.objects.all()
    serializer_class = HospitalProfileSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = None

    @action(detail=False, methods=['get'], url_path='current')
    def current(self, request):
        """Returns the primary active hospital profile."""
        profile = HospitalProfile.objects.filter(is_active=True).first()
        if not profile:
            profile = HospitalProfile.objects.first()
        if profile:
            serializer = self.get_serializer(profile)
            return response.Response(serializer.data)
        return response.Response(
            {"detail": "Hospital profile not configured."},
            status=404,
        )

    @action(detail=False, methods=['get'], url_path='profile')
    def profile(self, request):
        """Alias endpoint for active hospital profile."""
        return self.current(request)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAdminOrHospitalAdmin],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MediaUploadRateThrottle],
        url_path='upload-logo'
    )
    def upload_logo(self, request):
        """Uploads or replaces hospital emblem/logo."""
        profile = HospitalProfile.objects.filter(is_active=True).first() or HospitalProfile.objects.first()
        if not profile:
            return response.Response({"detail": "No hospital profile exists to attach logo."}, status=404)

        file_obj = request.FILES.get('logo') or request.FILES.get('image') or request.FILES.get('file')
        if not file_obj:
            return response.Response(
                {"detail": "No image file provided in request. Expected multipart field 'logo' or 'image'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        res = MediaService.replace_model_image(
            instance=profile,
            file_obj=file_obj,
            image_field_name='logo',
            public_id_field_name='logo_public_id',
            folder=CLOUDINARY_FOLDERS['hospital'],
        )
        profile.refresh_from_db()
        return response.Response({
            "message": "Hospital logo uploaded successfully.",
            "logo_url": res['url'],
            "public_id": res['public_id'],
            "profile": self.get_serializer(profile).data,
        }, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=['delete'],
        permission_classes=[IsAdminOrHospitalAdmin],
        url_path='delete-logo'
    )
    def delete_logo(self, request):
        """Removes hospital emblem/logo and destroys Cloudinary asset."""
        profile = HospitalProfile.objects.filter(is_active=True).first() or HospitalProfile.objects.first()
        if not profile:
            return response.Response({"detail": "No hospital profile configured."}, status=404)

        MediaService.delete_model_image(
            instance=profile,
            image_field_name='logo',
            public_id_field_name='logo_public_id',
        )
        profile.refresh_from_db()
        return response.Response({
            "message": "Hospital logo removed successfully.",
            "logo_url": None,
            "profile": self.get_serializer(profile).data,
        }, status=status.HTTP_200_OK)


class HospitalFacilityViewSet(viewsets.ModelViewSet):
    """
    Hospital clinical facilities and amenity units.
    """
    queryset = HospitalFacility.objects.filter(is_active=True)
    serializer_class = HospitalFacilitySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['order', 'name']
    ordering = ['order', 'name']

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAdminOrHospitalAdmin],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MediaUploadRateThrottle],
        url_path='upload-image'
    )
    def upload_image(self, request, pk=None):
        facility = self.get_object()
        file_obj = request.FILES.get('image') or request.FILES.get('file')
        if not file_obj:
            return response.Response(
                {"detail": "No image file provided. Expected multipart field 'image'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        res = MediaService.replace_model_image(
            instance=facility,
            file_obj=file_obj,
            image_field_name='image',
            public_id_field_name='image_public_id',
            folder=CLOUDINARY_FOLDERS['facilities'],
        )
        facility.refresh_from_db()
        return response.Response({
            "message": "Facility image uploaded successfully.",
            "facility_id": facility.id,
            "image_url": res['url'],
            "public_id": res['public_id'],
            "facility": self.get_serializer(facility).data,
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['delete'],
        permission_classes=[IsAdminOrHospitalAdmin],
        url_path='delete-image'
    )
    def delete_image(self, request, pk=None):
        facility = self.get_object()
        MediaService.delete_model_image(
            instance=facility,
            image_field_name='image',
            public_id_field_name='image_public_id',
        )
        facility.refresh_from_db()
        return response.Response({
            "message": "Facility image removed successfully.",
            "facility_id": facility.id,
            "image_url": None,
            "facility": self.get_serializer(facility).data,
        }, status=status.HTTP_200_OK)


class HospitalAnnouncementViewSet(viewsets.ModelViewSet):
    """
    Public health announcements, clinic advisories, and hospital news.
    Lookup by URL slug.
    """
    queryset = HospitalAnnouncement.objects.filter(is_published=True)
    serializer_class = HospitalAnnouncementSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_field = 'slug'
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_published']
    search_fields = ['title', 'summary', 'content']
    ordering_fields = ['published_at', 'created_at']
    ordering = ['-published_at', '-created_at']

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAdminOrHospitalAdmin],
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MediaUploadRateThrottle],
        url_path='upload-image'
    )
    def upload_image(self, request, slug=None):
        announcement = self.get_object()
        file_obj = request.FILES.get('image') or request.FILES.get('file')
        if not file_obj:
            return response.Response(
                {"detail": "No image file provided. Expected multipart field 'image'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        res = MediaService.replace_model_image(
            instance=announcement,
            file_obj=file_obj,
            image_field_name='image',
            public_id_field_name='image_public_id',
            folder=CLOUDINARY_FOLDERS['announcements'],
        )
        announcement.refresh_from_db()
        return response.Response({
            "message": "Announcement image uploaded successfully.",
            "announcement_id": announcement.id,
            "image_url": res['url'],
            "public_id": res['public_id'],
            "announcement": self.get_serializer(announcement).data,
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['delete'],
        permission_classes=[IsAdminOrHospitalAdmin],
        url_path='delete-image'
    )
    def delete_image(self, request, slug=None):
        announcement = self.get_object()
        MediaService.delete_model_image(
            instance=announcement,
            image_field_name='image',
            public_id_field_name='image_public_id',
        )
        announcement.refresh_from_db()
        return response.Response({
            "message": "Announcement image removed successfully.",
            "announcement_id": announcement.id,
            "image_url": None,
            "announcement": self.get_serializer(announcement).data,
        }, status=status.HTTP_200_OK)


class HospitalFAQViewSet(viewsets.ReadOnlyModelViewSet):
    """
    General institutional FAQs for patients and visitors.
    """
    queryset = HospitalFAQ.objects.filter(is_active=True)
    serializer_class = HospitalFAQSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['question', 'answer']
    ordering_fields = ['order', 'id']
    ordering = ['order', 'id']
