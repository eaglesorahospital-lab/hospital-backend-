from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, AuditLogViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')

audit_router = DefaultRouter()
audit_router.register(r'', AuditLogViewSet, basename='audit')

urlpatterns = [
    path('', include(router.urls)),
]
