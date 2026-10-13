from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DoctorScheduleViewSet,
    DoctorLeaveViewSet,
    ScheduleOverrideViewSet,
)

router = DefaultRouter()
router.register(r'leaves', DoctorLeaveViewSet, basename='leave')
router.register(r'overrides', ScheduleOverrideViewSet, basename='override')
router.register(r'', DoctorScheduleViewSet, basename='schedule')

urlpatterns = [
    path('', include(router.urls)),
]
