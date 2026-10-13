from rest_framework import serializers
from .models import Appointment
from apps.accounts.models import PatientProfile, User
from apps.doctors.models import Doctor
from apps.departments.models import Department


class AppointmentPatientNestedSerializer(serializers.ModelSerializer):
    """
    Compact patient details nested within appointment responses.
    """
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = PatientProfile
        fields = ['id', 'mrn', 'first_name', 'last_name', 'full_name', 'phone', 'email']


class AppointmentDoctorNestedSerializer(serializers.ModelSerializer):
    """
    Compact doctor details nested within appointment responses.
    """
    class Meta:
        model = Doctor
        fields = ['id', 'name', 'slug', 'specialty_name', 'consultation_location']


class AppointmentDepartmentNestedSerializer(serializers.ModelSerializer):
    """
    Compact department details nested within appointment responses.
    """
    class Meta:
        model = Department
        fields = ['id', 'name', 'slug', 'location']


class AppointmentListSerializer(serializers.ModelSerializer):
    """
    Appointment list summary serializer.
    """
    patient = AppointmentPatientNestedSerializer(read_only=True)
    doctor = AppointmentDoctorNestedSerializer(read_only=True)
    department = AppointmentDepartmentNestedSerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id',
            'reference',
            'patient',
            'doctor',
            'department',
            'appointment_date',
            'start_time',
            'end_time',
            'appointment_type',
            'consultation_location',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'reference', 'created_at']


class AppointmentDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive appointment details serializer including clinical notes
    and cancellation/rescheduling history.
    """
    patient = AppointmentPatientNestedSerializer(read_only=True)
    doctor = AppointmentDoctorNestedSerializer(read_only=True)
    department = AppointmentDepartmentNestedSerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id',
            'reference',
            'patient',
            'doctor',
            'department',
            'appointment_date',
            'start_time',
            'end_time',
            'appointment_type',
            'consultation_location',
            'status',
            'reason_for_visit',
            'notes',
            'cancellation_reason',
            'cancelled_at',
            'rescheduled_from',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference', 'created_at', 'updated_at']


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """
    Appointment creation serializer with input validation.
    Delegates authoritative booking and concurrency protection to AppointmentBookingService.
    """
    patient = serializers.PrimaryKeyRelatedField(
        queryset=PatientProfile.objects.all(),
        required=True,
    )
    doctor = serializers.PrimaryKeyRelatedField(
        queryset=Doctor.objects.all(),
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
    )

    class Meta:
        model = Appointment
        fields = [
            'id',
            'reference',
            'patient',
            'doctor',
            'department',
            'appointment_date',
            'start_time',
            'end_time',
            'appointment_type',
            'consultation_location',
            'status',
            'reason_for_visit',
            'notes',
        ]
        read_only_fields = ['id', 'reference', 'status', 'consultation_location', 'department']

    def validate(self, attrs):
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({
                'end_time': "Consultation end time must be after start time."
            })

        doctor = attrs.get('doctor')
        if doctor and not doctor.is_active:
            raise serializers.ValidationError({
                'doctor': "Cannot book appointment with an inactive doctor."
            })

        patient = attrs.get('patient')
        if patient and not patient.is_active:
            raise serializers.ValidationError({
                'patient': "Cannot book appointment for an inactive patient account."
            })

        return attrs


class AppointmentCancelSerializer(serializers.Serializer):
    """Serializer for appointment cancellation action."""
    reason = serializers.CharField(required=False, allow_blank=True, default="Cancelled by patient/staff.")


class AppointmentRescheduleSerializer(serializers.Serializer):
    """Serializer for appointment rescheduling action."""
    appointment_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs['start_time'] >= attrs['end_time']:
            raise serializers.ValidationError({
                'end_time': "Consultation end time must be after start time."
            })
        return attrs


class AppointmentUpdateSerializer(serializers.ModelSerializer):
    """
    Appointment update serializer with strict lifecycle state validation.
    """
    class Meta:
        model = Appointment
        fields = [
            'status',
            'reason_for_visit',
            'notes',
            'cancellation_reason',
            'cancelled_at',
            'appointment_type',
        ]

    def validate_status(self, value):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            from apps.accounts.models import User
            is_staff_or_admin = bool(
                request.user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
                or request.user.is_staff
                or request.user.is_superuser
            )
            if not is_staff_or_admin and self.instance and self.instance.status != value:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Patients are not permitted to modify appointment status.")

        if self.instance and self.instance.status != value:
            from apps.appointments.services import AppointmentBookingService, AppointmentStateError
            try:
                AppointmentBookingService.validate_transition(self.instance.status, value)
            except AppointmentStateError as e:
                raise serializers.ValidationError(str(e))
        return value

