import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.apps import apps
from django.db import connection

print("=== APPS AND MODELS INVENTORY ===")
for app_config in apps.get_app_configs():
    if app_config.name.startswith('apps.') or app_config.name.startswith('django_celery_beat'):
        models = app_config.get_models()
        print(f"\nApp: {app_config.name}")
        for model in models:
            count = model.objects.count()
            print(f"  - {model.__name__} ({model._meta.db_table}): {count} records")

print("\n=== RAW TABLES IN POSTGRESQL ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Total public tables: {len(tables)}")
    for t in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}";')
        cnt = cursor.fetchone()[0]
        print(f"  - {t}: {cnt} rows")
