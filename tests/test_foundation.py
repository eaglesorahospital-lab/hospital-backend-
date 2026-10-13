"""
Foundation verification tests for Hospital Platform (Phase 0).
Validates settings integrity, environment variable bindings, directory structures,
and required service configurations.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / 'backend'
FRONTEND_DIR = ROOT_DIR / 'frontend'

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def test_root_structure():
    """Verify all required top-level directories and files exist."""
    required_files = ['.env.example', '.gitignore', 'docker-compose.yml', 'README.md']
    required_dirs = ['frontend', 'backend', 'database', 'docs', 'docker', 'nginx', 'tests']

    for f in required_files:
        assert (ROOT_DIR / f).is_file(), f"Missing root file: {f}"
    for d in required_dirs:
        assert (ROOT_DIR / d).is_dir(), f"Missing root directory: {d}"


def test_docs_structure():
    """Verify all placeholder documentation files exist."""
    doc_files = ['API.md', 'ERD.md', 'ARCHITECTURE.md', 'DEPLOYMENT.md', 'TESTING.md']
    for doc in doc_files:
        path = ROOT_DIR / 'docs' / doc
        assert path.is_file(), f"Missing doc file: {doc}"
        assert 'Phase 0' in path.read_text(encoding='utf-8')


def test_docker_structure():
    """Verify all Dockerfiles and compose configuration exist."""
    assert (ROOT_DIR / 'docker' / 'frontend' / 'Dockerfile').is_file()
    assert (ROOT_DIR / 'docker' / 'backend' / 'Dockerfile').is_file()
    assert (ROOT_DIR / 'docker' / 'nginx' / 'Dockerfile').is_file()
    assert (ROOT_DIR / 'docker' / 'celery' / 'Dockerfile').is_file()
    assert (ROOT_DIR / 'nginx' / 'nginx.conf').is_file()


def test_frontend_structure():
    """Verify React application directory structure."""
    expected_dirs = [
        'public',
        'src/assets',
        'src/components/common',
        'src/components/layout',
        'src/components/hospital',
        'src/components/departments',
        'src/components/doctors',
        'src/components/appointments',
        'src/components/admin',
        'src/pages/public',
        'src/pages/doctors',
        'src/pages/appointments',
        'src/pages/patient',
        'src/pages/admin',
        'src/services',
        'src/data',
        'src/hooks',
        'src/layouts',
        'src/routes',
        'src/styles',
    ]
    for d in expected_dirs:
        assert (FRONTEND_DIR / d).is_dir(), f"Missing frontend directory: {d}"

    assert (FRONTEND_DIR / 'package.json').is_file()
    assert (FRONTEND_DIR / 'README.md').is_file()
    assert (FRONTEND_DIR / 'src' / 'App.jsx').is_file()


def test_backend_apps_structure():
    """Verify Django apps directories and apps.py configurations."""
    apps = [
        'accounts',
        'hospital',
        'departments',
        'doctors',
        'scheduling',
        'appointments',
        'notifications',
    ]
    for app in apps:
        app_dir = BACKEND_DIR / 'apps' / app
        assert app_dir.is_dir(), f"Missing app directory: {app}"
        assert (app_dir / '__init__.py').is_file()
        assert (app_dir / 'apps.py').is_file()


def test_env_example_no_secrets():
    """Verify .env.example contains placeholders and no actual credentials."""
    env_content = (ROOT_DIR / '.env.example').read_text(encoding='utf-8')
    assert 'DJANGO_SECRET_KEY=' in env_content
    assert 'DB_PASSWORD=' in env_content
    # Confirm no real .env committed
    assert not (ROOT_DIR / '.env').exists(), ".env must not exist in repository"


def test_django_settings_load_env():
    """Verify Django settings module loads environment variables correctly."""
    os.environ['DB_NAME'] = 'hosp_verify_db'
    os.environ['DB_USER'] = 'hosp_verify_user'
    os.environ['DB_HOST'] = 'hosp_verify_host'
    os.environ['DB_PORT'] = '5432'
    os.environ['REDIS_URL'] = 'redis://verify_redis:6379/3'

    import importlib
    from config import settings
    importlib.reload(settings)

    # Database checks
    default_db = settings.DATABASES['default']
    assert default_db['ENGINE'] == 'django.db.backends.postgresql'
    assert 'sqlite' not in default_db['ENGINE'].lower()
    assert default_db['NAME'] == 'hosp_verify_db'
    assert default_db['USER'] == 'hosp_verify_user'
    assert default_db['HOST'] == 'hosp_verify_host'

    # Redis & Cache checks
    assert 'redis' in settings.CACHES['default']['BACKEND'].lower()
    assert settings.CACHES['default']['LOCATION'] == 'redis://verify_redis:6379/3'

    # Celery checks
    assert hasattr(settings, 'CELERY_BROKER_URL')
    assert hasattr(settings, 'CELERY_RESULT_BACKEND')
    assert settings.CELERY_TASK_SERIALIZER == 'json'

    # DRF & SimpleJWT checks
    assert 'rest_framework' in settings.INSTALLED_APPS
    assert 'rest_framework_simplejwt' in settings.INSTALLED_APPS
    auth_classes = settings.REST_FRAMEWORK.get('DEFAULT_AUTHENTICATION_CLASSES', ())
    assert 'rest_framework_simplejwt.authentication.JWTAuthentication' in auth_classes

    # CORS checks
    assert 'corsheaders' in settings.INSTALLED_APPS
    assert hasattr(settings, 'CORS_ALLOWED_ORIGINS')

    # Optional Django setup check if django is installed in runtime
    try:
        import django
        django.setup()
        assert settings.configured is True
    except ImportError:
        pass


if __name__ == '__main__':
    print("Running Phase 0 Foundation Verification Tests...")
    test_root_structure()
    print("  [PASS] Root structure")
    test_docs_structure()
    print("  [PASS] Documentation structure")
    test_docker_structure()
    print("  [PASS] Docker configurations and Nginx")
    test_frontend_structure()
    print("  [PASS] Frontend directory structure and files")
    test_backend_apps_structure()
    print("  [PASS] Backend apps structure")
    test_env_example_no_secrets()
    print("  [PASS] .env.example placeholders and security check")
    test_django_settings_load_env()
    print("  [PASS] Django settings, PostgreSQL, Redis, Celery, DRF, SimpleJWT, CORS")
    print("\nALL PHASE 0 VERIFICATION TESTS PASSED SUCCESSFULLY!")
