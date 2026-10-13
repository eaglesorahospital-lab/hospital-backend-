"""
URL configuration for Hospital Platform project.
Provides API root namespace, service health checks, authentication (Phase 12),
and clinical domain REST APIs.
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.doctors.urls import specialties_router
from apps.notifications.urls import audit_router


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    """
    Hospital Platform API Root.
    Provides service status, active domain endpoints, and API metadata.
    """
    return Response({
        "service": "hospital-platform-api",
        "status": "active",
        "phase": "Phase 9 Foundation / Phase 11 REST API / Phase 12 Auth / Phase 13 Booking / Phase 14 Celery & Async Notifications",
        "version": "0.1.0",
        "endpoints": {
            "health": request.build_absolute_uri("health/"),
            "admin": request.build_absolute_uri("/admin/"),
            "auth": request.build_absolute_uri("auth/"),
            "hospital": request.build_absolute_uri("hospital/"),
            "departments": request.build_absolute_uri("departments/"),
            "specialties": request.build_absolute_uri("specialties/"),
            "doctors": request.build_absolute_uri("doctors/"),
            "schedules": request.build_absolute_uri("schedules/"),
            "appointments": request.build_absolute_uri("appointments/"),
            "patients": request.build_absolute_uri("patients/"),
            "administrators": request.build_absolute_uri("administrators/"),
            "notifications": request.build_absolute_uri("notifications/"),
            "audit": request.build_absolute_uri("audit/"),
        },
        "message": "Hospital Platform REST API Layer, Authentication & Async Processing operational."
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Service Health Check Endpoint.
    Lightweight, decoupled health probe for container orchestrators and load balancers.
    Default: fast response for Docker health checks.
    ?detailed=1: comprehensive probe verifying PostgreSQL and Redis connections.
    """
    details = {}
    is_healthy = True

    if request.query_params.get('detailed') == '1' or request.query_params.get('full') == '1':
        # Probe PostgreSQL Database
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
            details['database'] = 'connected'
        except Exception as e:
            details['database'] = f'error: {str(e)}'
            is_healthy = False

        # Probe Redis Cache
        try:
            from django.core.cache import cache
            cache.set('health_probe', '1', timeout=5)
            if cache.get('health_probe') == '1':
                details['redis'] = 'connected'
            else:
                details['redis'] = 'unresponsive'
                is_healthy = False
        except Exception as e:
            details['redis'] = f'error: {str(e)}'
            is_healthy = False

    response_data = {
        "status": "ok" if is_healthy else "degraded",
        "service": "hospital-platform-api"
    }
    if details:
        response_data["details"] = details

    status_code = 200 if is_healthy else 503
    return Response(response_data, status=status_code)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api_root, name='api_root'),
    path('api/health/', health_check, name='health_check'),
    path('api/auth/', include('apps.accounts.urls_auth')),
    path('api/hospital/', include('apps.hospital.urls')),
    path('api/departments/', include('apps.departments.urls')),
    path('api/specialties/', include(specialties_router.urls)),
    path('api/doctors/', include('apps.doctors.urls')),
    path('api/schedules/', include('apps.scheduling.urls')),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/patients/', include('apps.accounts.urls')),
    path('api/administrators/', include('apps.accounts.urls_admin')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/audit/', include(audit_router.urls)),
]
