"""
Accounts and RBAC service layer for Eagle Sora Hospital Platform.
Provides centralized helpers for managing user roles, groups, and permissions.
"""

import logging
from django.contrib.auth.models import Group, Permission
from .models import User

logger = logging.getLogger('hospital.accounts')

HOSPITAL_ADMIN_GROUP_NAME = 'Hospital Administrators'
HOSPITAL_MANAGED_APPS = [
    'hospital',
    'departments',
    'doctors',
    'scheduling',
    'appointments',
    'notifications',
    'accounts',
]


def get_or_create_hospital_admin_group():
    """
    Idempotently retrieves or creates the 'Hospital Administrators' Django Group,
    populating it with all model permissions across the hospital operational domains.
    """
    group, created = Group.objects.get_or_create(name=HOSPITAL_ADMIN_GROUP_NAME)
    hospital_perms = Permission.objects.filter(content_type__app_label__in=HOSPITAL_MANAGED_APPS)
    group.permissions.set(hospital_perms)
    if created:
        logger.info(f"Created '{HOSPITAL_ADMIN_GROUP_NAME}' group with {hospital_perms.count()} permissions.")
    return group


def setup_hospital_admin_user(user):
    """
    Configures a User as a Hospital Administrator:
    - Sets role to HOSPITAL_ADMIN
    - Sets is_staff to True for Django administration
    - Adds user to the 'Hospital Administrators' permission group
    """
    user.role = User.Role.HOSPITAL_ADMIN
    user.is_staff = True
    user.save(update_fields=['role', 'is_staff'])

    group = get_or_create_hospital_admin_group()
    user.groups.add(group)
    return user
