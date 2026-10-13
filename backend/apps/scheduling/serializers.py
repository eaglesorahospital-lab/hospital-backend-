from rest_framework import serializers
from .models import DoctorSchedule, ScheduleBreak, DoctorLeave, ScheduleOverride


class ScheduleBreakSerializer(serializers.ModelSerializer):
    """
    Break interval within a doctor's shift serializer.
    """
    class Meta:
        model = ScheduleBreak
        fields = ['id', 'name', 'start_time', 'end_time']
        read_only_fields = ['id']


class DoctorScheduleSerializer(serializers.ModelSerializer):
    """
    Doctor recurrent weekly operating schedule serializer.
    """
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    doctor_slug = serializers.CharField(source='doctor.slug', read_only=True)
    breaks = ScheduleBreakSerializer(many=True, read_only=True)

    class Meta:
        model = DoctorSchedule
        fields = [
            'id',
            'doctor',
            'doctor_name',
            'doctor_slug',
            'day_of_week',
            'start_time',
            'end_time',
            'slot_duration_minutes',
            'capacity',
            'timezone',
            'is_working_day',
            'is_active',
            'breaks',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DoctorLeaveSerializer(serializers.ModelSerializer):
    """
    Doctor planned absence and leave serializer.
    """
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    doctor_slug = serializers.CharField(source='doctor.slug', read_only=True)

    class Meta:
        model = DoctorLeave
        fields = [
            'id',
            'doctor',
            'doctor_name',
            'doctor_slug',
            'start_date',
            'end_date',
            'reason',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ScheduleOverrideSerializer(serializers.ModelSerializer):
    """
    Date-specific schedule override serializer.
    """
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    doctor_slug = serializers.CharField(source='doctor.slug', read_only=True)
    override_type_display = serializers.CharField(source='get_override_type_display', read_only=True)

    class Meta:
        model = ScheduleOverride
        fields = [
            'id',
            'doctor',
            'doctor_name',
            'doctor_slug',
            'override_date',
            'override_type',
            'override_type_display',
            'is_available',
            'start_time',
            'end_time',
            'slot_duration_minutes',
            'capacity',
            'reason',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def to_internal_value(self, data):
        # Normalize override_type if human label or legacy string is provided
        if isinstance(data, dict):
            data = data.copy()
            raw_type = data.get('override_type')
            if raw_type is not None:
                cleaned = str(raw_type).strip()
                type_map = {
                    'Special OPD': 'SPECIAL_OPD',
                    'special_opd': 'SPECIAL_OPD',
                    'SPECIAL_OPD': 'SPECIAL_OPD',
                    'Extended Hours': 'EXTENDED_HOURS',
                    'extended_hours': 'EXTENDED_HOURS',
                    'EXTENDED_HOURS': 'EXTENDED_HOURS',
                    'Reduced Hours': 'REDUCED_HOURS',
                    'reduced_hours': 'REDUCED_HOURS',
                    'REDUCED_HOURS': 'REDUCED_HOURS',
                    'Closed': 'CLOSED',
                    'closed': 'CLOSED',
                    'CLOSED': 'CLOSED',
                    'Unavailable': 'UNAVAILABLE',
                    'unavailable': 'UNAVAILABLE',
                    'UNAVAILABLE': 'UNAVAILABLE',
                    'Shift Adjustment': 'SHIFT_ADJUSTMENT',
                    'shift_adjustment': 'SHIFT_ADJUSTMENT',
                    'SHIFT_ADJUSTMENT': 'SHIFT_ADJUSTMENT',
                    'Emergency Cover': 'EMERGENCY_COVER',
                    'emergency_cover': 'EMERGENCY_COVER',
                    'EMERGENCY_COVER': 'EMERGENCY_COVER',
                }
                normalized_type = type_map.get(cleaned, cleaned)
                data['override_type'] = normalized_type

                # For Closed/Unavailable, force is_available=False and nullify start/end times
                if normalized_type in ('CLOSED', 'UNAVAILABLE'):
                    data['is_available'] = False
                    data['start_time'] = None
                    data['end_time'] = None
                else:
                    if 'is_available' not in data:
                        data['is_available'] = True

            # If times are empty strings, convert to None so TimeField does not error
            if data.get('start_time') == '':
                data['start_time'] = None
            if data.get('end_time') == '':
                data['end_time'] = None

        return super().to_internal_value(data)

    def validate(self, attrs):
        override_type = attrs.get('override_type')
        is_available = attrs.get('is_available', True)
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        if override_type in (ScheduleOverride.OverrideType.CLOSED, ScheduleOverride.OverrideType.UNAVAILABLE) or not is_available:
            attrs['is_available'] = False
            attrs['start_time'] = None
            attrs['end_time'] = None
        else:
            attrs['is_available'] = True
            if not start_time:
                raise serializers.ValidationError({'start_time': 'Start time is required for open clinic overrides.'})
            if not end_time:
                raise serializers.ValidationError({'end_time': 'End time is required for open clinic overrides.'})
            if start_time >= end_time:
                raise serializers.ValidationError({'end_time': 'End time must be later than start time.'})

        return attrs
