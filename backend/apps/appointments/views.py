from datetime import datetime, time, timedelta
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import PermissionDenied
from .models import Appointment
from .serializers import (
    AppointmentListSerializer,
    AppointmentDetailSerializer,
    AppointmentCreateSerializer,
    AppointmentUpdateSerializer,
    AppointmentCancelSerializer,
    AppointmentRescheduleSerializer,
)
from .services import (
    AppointmentBookingService,
    SlotConflictError,
    SlotValidationError,
    AppointmentStateError,
)
from apps.accounts.models import User, PatientProfile
from apps.doctors.models import Doctor
from apps.accounts.permissions import IsPatientOwnerOrStaff
from apps.notifications.services import safe_dispatch_confirmation
from config.pagination import StandardResultsSetPagination
from config.throttling import AppointmentBookingRateThrottle


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Appointment management and query API.
    Protected by RBAC and object-level authorization:
    - Patients can only view, create, cancel, and reschedule their own appointments.
    - Doctor staff view appointments assigned to their clinical schedules.
    - Administrators have platform-wide consultation management access.
    - Anonymous requests are rejected (401).
    - Booking uses PostgreSQL row-locking and atomic transaction protection.
    """
    permission_classes = [permissions.IsAuthenticated, IsPatientOwnerOrStaff]
    lookup_field = 'reference'
    lookup_value_regex = r'[^/]+'
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'status',
        'appointment_type',
        'appointment_date',
        'doctor',
        'doctor__slug',
        'patient',
        'patient__mrn',
        'department',
        'department__slug',
    ]
    search_fields = [
        'reference',
        'patient__first_name',
        'patient__last_name',
        'patient__mrn',
        'doctor__name',
        'reason_for_visit',
    ]
    ordering_fields = ['appointment_date', 'start_time', 'created_at', 'status']
    ordering = ['-appointment_date', '-start_time']

    def get_throttles(self):
        if self.action == 'create':
            return [AppointmentBookingRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Appointment.objects.none()

        base_qs = Appointment.objects.select_related(
            'patient',
            'patient__user',
            'doctor',
            'doctor__specialty',
            'department',
        )

        # Platform and hospital administrators view all consultations
        if (
            user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN]
            or user.is_superuser
            or user.is_staff
        ):
            return base_qs

        # Doctor staff view appointments assigned to their doctor profile
        if user.role == User.Role.DOCTOR_STAFF:
            if hasattr(user, 'doctor_profile') and user.doctor_profile:
                return base_qs.filter(doctor=user.doctor_profile)
            return base_qs

        # Patients are strictly isolated to their own bookings
        return base_qs.filter(patient__user=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action in ['update', 'partial_update']:
            return AppointmentUpdateSerializer
        if self.action == 'retrieve':
            return AppointmentDetailSerializer
        if self.action == 'cancel':
            return AppointmentCancelSerializer
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentListSerializer

    def create(self, request, *args, **kwargs):
        """
        Transactional booking with concurrency protection, availability re-check,
        and PostgreSQL row locking.
        """
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        user = request.user

        # Patient resolution: authenticated patients must book for their own profile
        if user.role == User.Role.PATIENT:
            patient_profile = getattr(user, 'patient_profile', None)
            if not patient_profile and user.email:
                patient_profile = PatientProfile.objects.filter(email__iexact=user.email, user__isnull=True).first()
                if patient_profile:
                    patient_profile.user = user
                    patient_profile.save(update_fields=['user'])
            if not patient_profile:
                patient_profile = PatientProfile.objects.create(
                    user=user,
                    first_name=user.first_name or "Patient",
                    last_name=user.last_name or "",
                    email=user.email,
                    phone=user.phone or "",
                    is_active=True,
                )
            data['patient'] = patient_profile.id

        serializer = AppointmentCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        doctor = serializer.validated_data['doctor']
        appointment_date = serializer.validated_data['appointment_date']
        start_time = serializer.validated_data['start_time']
        end_time = serializer.validated_data['end_time']
        appointment_type = serializer.validated_data.get(
            'appointment_type', Appointment.AppointmentType.IN_PERSON
        )
        reason_for_visit = serializer.validated_data.get('reason_for_visit', '')
        notes = serializer.validated_data.get('notes', '')

        patient = user.patient_profile if user.role == User.Role.PATIENT else serializer.validated_data['patient']

        # Idempotency header
        idempotency_key = request.headers.get('Idempotency-Key') or request.META.get('HTTP_IDEMPOTENCY_KEY')

        # Resolve status: Patients ALWAYS create with REQUESTED.
        # Staff/Admins can specify status if needed, but defaults to REQUESTED.
        booking_status = Appointment.Status.REQUESTED
        is_staff_or_admin = bool(
            user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
            or user.is_staff
            or user.is_superuser
        )
        if is_staff_or_admin and 'status' in data and data['status'] in Appointment.Status.values:
            booking_status = data['status']

        try:
            appointment, created = AppointmentBookingService.book_appointment(
                patient=patient,
                doctor=doctor,
                appointment_date=appointment_date,
                start_time=start_time,
                end_time=end_time,
                appointment_type=appointment_type,
                status=booking_status,
                reason_for_visit=reason_for_visit,
                notes=notes,
                idempotency_key=idempotency_key,
            )
            response_data = AppointmentDetailSerializer(appointment).data
            return Response(
                response_data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        except SlotConflictError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except (SlotValidationError, AppointmentStateError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_update(self, serializer):
        old_status = self.get_object().status
        instance = serializer.save()
        if old_status == Appointment.Status.REQUESTED and instance.status == Appointment.Status.CONFIRMED:
            safe_dispatch_confirmation(instance.id)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(AppointmentDetailSerializer(instance).data)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, reference=None):
        """
        Manually approves a REQUESTED appointment, transitioning it to CONFIRMED.
        Restricted to authorized hospital staff and administrators.
        """
        user = request.user
        if not (
            user
            and user.is_authenticated
            and (
                user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
                or user.is_staff
                or user.is_superuser
            )
        ):
            raise PermissionDenied("Only authorized staff and administrators can approve appointments.")

        apt = self.get_object()
        if apt.status != Appointment.Status.REQUESTED:
            return Response(
                {"detail": f"Cannot approve appointment with status '{apt.status}'. Only REQUESTED appointments can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        apt.status = Appointment.Status.CONFIRMED
        apt.save(update_fields=['status', 'updated_at'])

        safe_dispatch_confirmation(apt.id)

        return Response(AppointmentDetailSerializer(apt).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, reference=None):
        """
        Cancels an appointment with status validation and state update.
        """
        apt = self.get_object()
        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', '')

        try:
            cancelled_apt = AppointmentBookingService.cancel_appointment(
                appointment_identifier=apt,
                user=request.user,
                reason=reason,
            )
            return Response(AppointmentDetailSerializer(cancelled_apt).data, status=status.HTTP_200_OK)
        except AppointmentStateError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

    @action(detail=True, methods=['post'], url_path='reschedule')
    def reschedule(self, request, reference=None):
        """
        Reschedules an appointment atomically. Validates target slot availability.
        If unavailable, rolls back leaving original appointment untouched.
        """
        apt = self.get_object()
        serializer = AppointmentRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_date = serializer.validated_data['appointment_date']
        new_start_time = serializer.validated_data['start_time']
        new_end_time = serializer.validated_data['end_time']
        reason = serializer.validated_data.get('reason', '')

        try:
            new_apt = AppointmentBookingService.reschedule_appointment(
                appointment_identifier=apt,
                user=request.user,
                new_date=new_date,
                new_start_time=new_start_time,
                new_end_time=new_end_time,
                reason=reason,
            )
            return Response(AppointmentDetailSerializer(new_apt).data, status=status.HTTP_200_OK)
        except SlotConflictError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except (SlotValidationError, AppointmentStateError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny], url_path='book')
    def public_book(self, request):
        """
        Public and outpatient appointment booking action.
        Supports atomic creation of patient profile and appointment with PostgreSQL row-locking
        and concurrency protection.
        """
        data = request.data
        doctor_val = data.get('doctor') or data.get('doctorId') or data.get('doctor_id')
        doctor = None
        if isinstance(doctor_val, int) or (isinstance(doctor_val, str) and doctor_val.isdigit()):
            doctor = Doctor.objects.filter(id=int(doctor_val)).first()
        elif doctor_val:
            doctor = Doctor.objects.filter(slug=str(doctor_val)).first()

        if not doctor:
            return Response(
                {"detail": "A valid doctor (id or slug) is required for booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appointment_date = data.get('appointment_date') or data.get('date')
        if not appointment_date:
            return Response(
                {"detail": "Appointment date is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_time_str = data.get('start_time') or data.get('time')
        if not start_time_str:
            return Response(
                {"detail": "Appointment start_time is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed_start = None
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
            try:
                parsed_start = datetime.strptime(start_time_str.strip(), fmt).time()
                break
            except ValueError:
                pass
        if not parsed_start:
            return Response(
                {"detail": f"Invalid start_time format '{start_time_str}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        end_time_str = data.get('end_time')
        parsed_end = None
        if end_time_str:
            for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
                try:
                    parsed_end = datetime.strptime(end_time_str.strip(), fmt).time()
                    break
                except ValueError:
                    pass

        if not parsed_end:
            duration = doctor.consultation_duration_minutes or 30
            dt_start = datetime.combine(datetime.today(), parsed_start)
            parsed_end = (dt_start + timedelta(minutes=duration)).time()

        patient_data = data.get('patient') or {}
        patient_profile = None

        if request.user and request.user.is_authenticated:
            if hasattr(request.user, 'patient_profile') and request.user.patient_profile:
                patient_profile = request.user.patient_profile
            elif request.user.role == User.Role.PATIENT:
                # Link or create for authenticated patient
                phone = (patient_data.get('mobile') or patient_data.get('phone') or getattr(request.user, 'phone', '') or '').strip()
                email = getattr(request.user, 'email', '') or (patient_data.get('email') or '').strip()
                if email:
                    patient_profile = PatientProfile.objects.filter(email__iexact=email, user__isnull=True).first()
                if not patient_profile and phone:
                    patient_profile = PatientProfile.objects.filter(phone=phone, user__isnull=True).first()
                if patient_profile:
                    patient_profile.user = request.user
                    patient_profile.save(update_fields=['user'])
                else:
                    full_name = patient_data.get('fullName') or patient_data.get('name') or request.user.get_full_name() or "Patient"
                    parts = full_name.strip().split()
                    first_name = parts[0] if parts else "Patient"
                    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                    patient_profile = PatientProfile.objects.create(
                        user=request.user,
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        email=email,
                        is_active=True,
                    )

        # For unauthenticated requests, do NOT trust client-supplied patient_id!
        # Only allow staff users to specify an arbitrary patient_id
        if not patient_profile:
            is_staff_user = (
                request.user
                and request.user.is_authenticated
                and (
                    request.user.role in [User.Role.SUPER_ADMIN, User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR_STAFF]
                    or request.user.is_staff
                )
            )
            if is_staff_user and data.get('patient_id'):
                patient_profile = PatientProfile.objects.filter(id=data['patient_id']).first()

        if not patient_profile:
            # Unauthenticated guest flow: find existing unlinked guest profile or create a new guest profile
            phone = (patient_data.get('mobile') or patient_data.get('phone') or '').strip()
            email = (patient_data.get('email') or '').strip()

            if phone:
                patient_profile = PatientProfile.objects.filter(phone=phone, user__isnull=True).first()
            if not patient_profile and email:
                patient_profile = PatientProfile.objects.filter(email__iexact=email, user__isnull=True).first()

            if not patient_profile:
                full_name = patient_data.get('fullName') or patient_data.get('name') or "Guest Patient"
                parts = full_name.strip().split()
                first_name = parts[0] if parts else "Guest"
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

                gender_input = str(patient_data.get('gender') or 'MALE').upper()
                gender_choice = PatientProfile.Gender.MALE
                for choice in PatientProfile.Gender.choices:
                    if choice[0] == gender_input or choice[1].upper() == gender_input:
                        gender_choice = choice[0]
                        break

                dob = patient_data.get('dateOfBirth') or patient_data.get('dob') or None
                if dob:
                    try:
                        datetime.strptime(dob, "%Y-%m-%d")
                    except ValueError:
                        dob = None

                patient_profile = PatientProfile.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    email=email,
                    date_of_birth=dob,
                    gender=gender_choice,
                    address=patient_data.get('address', ''),
                    emergency_contact=patient_data.get('emergencyContact', ''),
                    is_active=True,
                )

        reason_for_visit = data.get('reason_for_visit') or patient_data.get('reasonForVisit') or 'Clinical consultation'
        notes = data.get('notes') or ''
        idempotency_key = request.headers.get('Idempotency-Key') or data.get('idempotency_key')

        try:
            appointment, created = AppointmentBookingService.book_appointment(
                patient=patient_profile,
                doctor=doctor,
                appointment_date=appointment_date,
                start_time=parsed_start,
                end_time=parsed_end,
                appointment_type=Appointment.AppointmentType.IN_PERSON,
                status=Appointment.Status.REQUESTED,
                reason_for_visit=reason_for_visit,
                notes=notes,
                idempotency_key=idempotency_key,
            )
            response_data = AppointmentDetailSerializer(appointment).data
            return Response(response_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except SlotConflictError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except (SlotValidationError, AppointmentStateError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
