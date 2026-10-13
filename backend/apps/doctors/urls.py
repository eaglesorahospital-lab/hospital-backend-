from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DoctorViewSet, SpecialtyViewSet

router = DefaultRouter()
router.register(r'', DoctorViewSet, basename='doctor')

specialties_router = DefaultRouter()
specialties_router.register(r'', SpecialtyViewSet, basename='specialty')

urlpatterns = [
    path('', include(router.urls)),
]
