from django.contrib import admin
from .models import Department, DepartmentService, DepartmentFAQ

admin.site.register(Department)
admin.site.register(DepartmentService)
admin.site.register(DepartmentFAQ)
