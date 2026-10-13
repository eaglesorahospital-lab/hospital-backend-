"""
Backend foundation verification tests for Hospital Platform (Phase 9).
Validates Django configuration, API root, health check, DRF settings,
PostgreSQL config structure, Redis, Celery, SimpleJWT, and Phase 9 boundary constraints.
Uses SimpleTestCase (databases = []) so tests execute cleanly without requiring a live database.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.test import SimpleTestCase
from rest_framework.test import APIClient
from django.conf import settings
from django.apps import apps


class BackendFoundationTests(SimpleTestCase):
    """Phase 9 Backend Foundation test suite."""
    databases = []  # Explicitly decoupled from live database requirement

    def setUp(self):
        self.client = APIClient()

    def test_django_configuration_loads(self):
        """Verify Django settings load and the framework is configured."""
        self.assertTrue(settings.configured)
        self.assertEqual(settings.ROOT_URLCONF, 'config.urls')
        self.assertEqual(settings.WSGI_APPLICATION, 'config.wsgi.application')

    def test_api_root_endpoint_responds(self):
        """Verify GET /api/ responds with 200 OK and valid service metadata."""
        response = self.client.get('/api/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('service'), 'hospital-platform-api')
        self.assertEqual(data.get('status'), 'active')
        self.assertIn('Phase 9', data.get('phase', ''))
        self.assertIn('health', data.get('endpoints', {}))

    def test_health_check_endpoint_responds(self):
        """Verify GET /api/health/ responds with status ok and service identifier."""
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'hospital-platform-api')

    def test_health_response_is_valid_json(self):
        """Verify /api/health/ content type is JSON."""
        response = self.client.get('/api/health/')
        content_type = response.headers.get('Content-Type', '')
        self.assertTrue(
            content_type.startswith('application/json'),
            f"Expected application/json, got {content_type}"
        )

    def test_drf_and_simplejwt_configuration(self):
        """Verify Django REST Framework and SimpleJWT settings."""
        self.assertIn('rest_framework', settings.INSTALLED_APPS)
        self.assertIn('rest_framework_simplejwt', settings.INSTALLED_APPS)

        auth_classes = settings.REST_FRAMEWORK.get('DEFAULT_AUTHENTICATION_CLASSES', ())
        self.assertIn(
            'rest_framework_simplejwt.authentication.JWTAuthentication',
            auth_classes
        )

        # Check SimpleJWT token lifetime configuration
        self.assertTrue(hasattr(settings, 'SIMPLE_JWT'))
        self.assertIn('ACCESS_TOKEN_LIFETIME', settings.SIMPLE_JWT)
        self.assertIn('REFRESH_TOKEN_LIFETIME', settings.SIMPLE_JWT)

    def test_postgresql_configuration_structure(self):
        """Verify PostgreSQL is the configured database engine (SQLite prohibited)."""
        db_config = settings.DATABASES['default']
        self.assertEqual(db_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertNotIn('sqlite', db_config['ENGINE'].lower())
        self.assertTrue(db_config['NAME'])
        self.assertTrue(db_config['USER'])

    def test_cors_configuration(self):
        """Verify CORS middleware and origin configuration."""
        self.assertIn('corsheaders', settings.INSTALLED_APPS)
        self.assertIn('corsheaders.middleware.CorsMiddleware', settings.MIDDLEWARE)
        self.assertTrue(hasattr(settings, 'CORS_ALLOWED_ORIGINS'))
        self.assertIsInstance(settings.CORS_ALLOWED_ORIGINS, list)
        self.assertTrue(len(settings.CORS_ALLOWED_ORIGINS) > 0)

    def test_redis_cache_configuration(self):
        """Verify Redis cache configuration."""
        cache_config = settings.CACHES['default']
        self.assertIn('redis', cache_config['BACKEND'].lower())
        self.assertTrue(hasattr(settings, 'REDIS_URL'))

    def test_celery_and_beat_configuration(self):
        """Verify Celery broker, result backend, and Celery Beat scheduler."""
        self.assertTrue(hasattr(settings, 'CELERY_BROKER_URL'))
        self.assertTrue(hasattr(settings, 'CELERY_RESULT_BACKEND'))
        self.assertTrue(hasattr(settings, 'CELERY_BEAT_SCHEDULER'))
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULER,
            'django_celery_beat.schedulers:DatabaseScheduler'
        )

    def test_smtp_and_email_configuration(self):
        """Verify SMTP / transactional email configuration."""
        self.assertTrue(hasattr(settings, 'EMAIL_HOST'))
        self.assertTrue(hasattr(settings, 'EMAIL_PORT'))
        self.assertTrue(hasattr(settings, 'DEFAULT_FROM_EMAIL'))

    def test_phase_10_domain_models_registered(self):
        """Verify Phase 10 domain models are properly registered across all clinical apps."""
        expected_counts = {
            'accounts': 2,       # User, PatientProfile
            'hospital': 4,       # HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ
            'departments': 3,    # Department, DepartmentService, DepartmentFAQ
            'doctors': 2,        # Specialty, Doctor
            'scheduling': 4,     # DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride
            'appointments': 1,   # Appointment
            'notifications': 2,  # Notification, AuditLog
        }
        for app_label, count in expected_counts.items():
            app_config = apps.get_app_config(app_label)
            models = list(app_config.get_models())
            self.assertEqual(
                len(models),
                count,
                f"App {app_label} expected {count} models, found {len(models)}: {models}"
            )


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_backend_foundation'])
    sys.exit(bool(failures))
