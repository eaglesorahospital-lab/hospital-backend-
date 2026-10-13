from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HospitalProfileViewSet,
    HospitalFacilityViewSet,
    HospitalAnnouncementViewSet,
    HospitalFAQViewSet,
)

router = DefaultRouter()
router.register(r'facilities', HospitalFacilityViewSet, basename='facility')
router.register(r'announcements', HospitalAnnouncementViewSet, basename='announcement')
router.register(r'faqs', HospitalFAQViewSet, basename='faq')
router.register(r'', HospitalProfileViewSet, basename='profile')

urlpatterns = [
    path('', include(router.urls)),
]
