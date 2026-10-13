from django.contrib import admin
from .models import Notification, AuditLog

admin.site.register(Notification)
admin.site.register(AuditLog)
