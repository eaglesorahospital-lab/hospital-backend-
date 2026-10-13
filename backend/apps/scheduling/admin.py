from django.contrib import admin
from .models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride

admin.site.register(DoctorSchedule)
admin.site.register(ScheduleBreak)
admin.site.register(DoctorLeave)
admin.site.register(ScheduleOverride)
