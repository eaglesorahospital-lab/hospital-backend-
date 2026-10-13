from rest_framework import serializers
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from .models import PatientProfile

User = get_user_model()


class UserMinimalSerializer(serializers.ModelSerializer):
    """
    Sanitized read-only user identity representation.
    Strictly excludes passwords, hashes, and internal permissions.
    """
    name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'first_name', 'last_name', 'phone', 'role', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined']


class PatientProfileSummarySerializer(serializers.ModelSerializer):
    """
    Compact patient profile summary for current user profile.
    """
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            'id',
            'mrn',
            'full_name',
            'first_name',
            'last_name',
            'email',
            'phone',
            'gender',
            'blood_group',
            'date_of_birth',
            'emergency_contact',
            'address',
        ]
        read_only_fields = fields


class CurrentUserSerializer(serializers.ModelSerializer):
    """
    Sanitized authenticated user details for /api/auth/me/.
    Never exposes passwords, hashes, or sensitive internals.
    """
    name = serializers.CharField(source='get_full_name', read_only=True)
    patient_profile = PatientProfileSummarySerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'phone',
            'role',
            'is_active',
            'date_joined',
            'patient_profile',
        ]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """
    Authentication credential validator.
    Prevents credential enumeration by returning generic error messages.
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        password = attrs.get('password', '')

        if not email or not password:
            raise serializers.ValidationError({"detail": "Must include email and password."})

        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(password) or not user.is_active:
            raise serializers.ValidationError({"detail": "Invalid email or password."})

        attrs['user'] = user
        return attrs


class RegisterPatientSerializer(serializers.Serializer):
    """
    Public outpatient registration serializer.
    Strictly enforces PATIENT role; privileged role escalation is impossible.
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=PatientProfile.Gender.choices, required=False, default=PatientProfile.Gender.MALE)
    blood_group = serializers.ChoiceField(choices=PatientProfile.BloodGroup.choices, required=False, allow_blank=True)
    emergency_contact = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        # Convert empty string date_of_birth to None so DateField does not fail validation
        if 'date_of_birth' in data and (data['date_of_birth'] == '' or data['date_of_birth'] is None):
            data['date_of_birth'] = None
        if 'gender' in data and isinstance(data['gender'], str):
            data['gender'] = data['gender'].strip().upper()
        if 'blood_group' in data and (data['blood_group'] == '' or data['blood_group'] is None):
            data['blood_group'] = ''
        return super().to_internal_value(data)

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Password fields do not match."})

        # Validate password strength against Django configured validators
        try:
            password_validation.validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        email = validated_data.pop('email').strip().lower()
        password = validated_data.pop('password')
        first_name = validated_data.pop('first_name', '').strip()
        last_name = validated_data.pop('last_name', '').strip()
        phone = validated_data.pop('phone', '').strip()

        with transaction.atomic():
            # Strictly enforce PATIENT role
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=User.Role.PATIENT,
            )

            # Create linked outpatient demographic profile
            PatientProfile.objects.create(
                user=user,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                date_of_birth=validated_data.get('date_of_birth'),
                gender=validated_data.get('gender', PatientProfile.Gender.MALE),
                blood_group=validated_data.get('blood_group', ''),
                emergency_contact=validated_data.get('emergency_contact', ''),
                address=validated_data.get('address', ''),
            )

            return user


class LogoutSerializer(serializers.Serializer):
    """
    Refresh token invalidation serializer for logout.
    """
    refresh = serializers.CharField()


class PatientProfileSerializer(serializers.ModelSerializer):
    """
    Outpatient demographic and identification serializer.
    """
    full_name = serializers.CharField(read_only=True)
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            'id',
            'mrn',
            'user',
            'first_name',
            'last_name',
            'full_name',
            'date_of_birth',
            'gender',
            'phone',
            'email',
            'blood_group',
            'emergency_contact',
            'address',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'mrn', 'created_at', 'updated_at']


class PatientProfileCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating patient records.
    """
    class Meta:
        model = PatientProfile
        fields = [
            'id',
            'mrn',
            'user',
            'first_name',
            'last_name',
            'date_of_birth',
            'gender',
            'phone',
            'email',
            'blood_group',
            'emergency_contact',
            'address',
            'is_active',
        ]
        read_only_fields = ['id', 'mrn']


class AdministratorSerializer(serializers.ModelSerializer):
    """
    Sanitized representation of hospital administrators (SUPER_ADMIN and HOSPITAL_ADMIN).
    Strictly excludes passwords and password hashes.
    """
    name = serializers.CharField(source='get_full_name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'phone',
            'role',
            'role_display',
            'is_staff',
            'is_active',
            'is_superuser',
            'date_joined',
            'last_login',
        ]
        read_only_fields = [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'phone',
            'role',
            'role_display',
            'is_staff',
            'is_superuser',
            'date_joined',
            'last_login',
        ]


class AdministratorCreateSerializer(serializers.Serializer):
    """
    Serializer for provisioning new Hospital Administrator accounts.
    - Requires full name (or first/last name), unique email, and password.
    - Strictly hashes password using Django's authentication hasher.
    - Assigns role HOSPITAL_ADMIN, is_staff=True, is_active=True.
    - Assigns user to 'Hospital Administrators' permission group.
    """
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Password fields do not match."})

        # Validate password against Django configured validators
        try:
            password_validation.validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        # Parse full_name if first_name/last_name not explicitly provided
        full_name = attrs.get('full_name', '').strip()
        first_name = attrs.get('first_name', '').strip()
        last_name = attrs.get('last_name', '').strip()

        if full_name and not first_name and not last_name:
            parts = full_name.split(' ', 1)
            attrs['first_name'] = parts[0]
            attrs['last_name'] = parts[1] if len(parts) > 1 else ''
        elif not first_name and not last_name and not full_name:
            raise serializers.ValidationError({"full_name": "Full name is required."})

        return attrs

    def create(self, validated_data):
        from .services import setup_hospital_admin_user

        validated_data.pop('password_confirm', None)
        validated_data.pop('full_name', None)
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        phone = validated_data.get('phone', '')

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=User.Role.HOSPITAL_ADMIN,
            is_staff=True,
            is_active=True,
        )

        setup_hospital_admin_user(user)
        return user

