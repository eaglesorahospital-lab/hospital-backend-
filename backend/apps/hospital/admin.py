from django.contrib import admin
from .models import HospitalProfile, HospitalFacility, HospitalAnnouncement, HospitalFAQ

admin.site.register(HospitalProfile)
admin.site.register(HospitalFacility)
admin.site.register(HospitalAnnouncement)
admin.site.register(HospitalFAQ)
