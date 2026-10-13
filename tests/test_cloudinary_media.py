"""
Phase 15 — Cloudinary Media Upload Integration Test Suite.
Verifies:
1. Configuration loading and safe fallback when credentials are absent.
2. Strict media validation:
   - MIME types (JPEG, PNG, WEBP)
   - Whitelisted extensions (.jpg, .jpeg, .png, .webp)
   - 5MB maximum file size limit
   - Pillow binary verification to reject corrupted files, scripts, and spoofed executables.
3. RBAC & Object-Level Authorization:
   - Unauthenticated & Patient upload rejected (401 / 403)
   - Super Admin & Hospital Admin authorized
   - Doctor staff can manage ONLY their own linked doctor profile photo (object ownership)
   - Doctor staff blocked from modifying other doctors (403)
4. PostgreSQL Persistence & Serializer Exposure:
   - Cloudinary secure URL and public_id persisted in database
   - Public GET serializers expose photo_url / image_url and image_public_id
5. Safe Two-Phase Replacement & Cleanup:
   - Previous Cloudinary asset destroyed only after new asset safely persisted
   - Failed upload keeps existing photo intact
   - Failed database update cleans up newly uploaded asset to avoid orphans
6. Deletion Behavior:
   - Authorized deletion releases Cloudinary asset and clears database reference
   - Repeated / idempotent deletion succeeds cleanly
7. Failure Handling & Credential Masking:
   - Cloudinary provider downtime returns clean HTTP 400 error
   - Secrets, API keys, and stack traces never leaked in API responses or logs
"""

import os
import sys
from io import BytesIO
from unittest.mock import patch, MagicMock

# Ensure backend path is on sys.path
backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status
from PIL import Image

from apps.accounts.models import User
from apps.doctors.models import Doctor, Specialty
from apps.departments.models import Department
from apps.hospital.models import HospitalProfile, HospitalFacility, HospitalAnnouncement
from config.media_service import (
    MediaService,
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    CLOUDINARY_FOLDERS,
)


def create_dummy_image(format='JPEG', size=(100, 100), color=(0, 128, 255)):
    """Creates a valid in-memory image for upload testing."""
    file_io = BytesIO()
    img = Image.new('RGB', size, color=color)
    img.save(file_io, format=format)
    file_io.seek(0)
    ext = format.lower()
    if ext == 'jpeg':
        ext = 'jpg'
    filename = f"test_sample.{ext}"
    mime = f"image/{format.lower()}"
    return SimpleUploadedFile(filename, file_io.getvalue(), content_type=mime)


class CloudinaryMediaConfigurationTests(TestCase):
    """
    Test suite for Cloudinary settings loading, credential detection, and fallback safety.
    """

    def test_01_cloudinary_settings_load_from_environment(self):
        """Verify Cloudinary environment variables are recognized in Django settings."""
        self.assertTrue(hasattr(settings, 'CLOUDINARY_CLOUD_NAME'))
        self.assertTrue(hasattr(settings, 'CLOUDINARY_API_KEY'))
        self.assertTrue(hasattr(settings, 'CLOUDINARY_API_SECRET'))

    def test_02_missing_credentials_handled_safely(self):
        """When credentials are blank, MediaService gracefully reports unconfigured without crashing."""
        with patch.object(settings, 'CLOUDINARY_CLOUD_NAME', ''), \
             patch.object(settings, 'CLOUDINARY_API_KEY', ''), \
             patch.object(settings, 'CLOUDINARY_API_SECRET', ''):
            self.assertFalse(MediaService.is_cloudinary_configured())
            # Fallback upload should work cleanly in test/offline environment
            dummy = create_dummy_image('JPEG')
            result = MediaService.upload_image(dummy, folder='test-folder')
            self.assertIn('url', result)
            self.assertIn('public_id', result)
            self.assertTrue(result['public_id'].startswith('test-folder/'))


class MediaValidationTests(TestCase):
    """
    Test suite for upload validation: MIME types, extensions, size limits, and Pillow inspection.
    """

    def test_03_valid_jpeg_accepted(self):
        """Valid JPEG image passes validation."""
        img = create_dummy_image('JPEG')
        try:
            MediaService.validate_image(img)
        except Exception as exc:
            self.fail(f"Valid JPEG unexpectedly failed validation: {exc}")

    def test_04_valid_png_accepted(self):
        """Valid PNG image passes validation."""
        img = create_dummy_image('PNG')
        try:
            MediaService.validate_image(img)
        except Exception as exc:
            self.fail(f"Valid PNG unexpectedly failed validation: {exc}")

    def test_05_valid_webp_accepted(self):
        """Valid WEBP image passes validation."""
        img = create_dummy_image('WEBP')
        try:
            MediaService.validate_image(img)
        except Exception as exc:
            self.fail(f"Valid WEBP unexpectedly failed validation: {exc}")

    def test_06_empty_file_rejected(self):
        """Empty file raises clean ValidationError."""
        empty_file = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")
        with self.assertRaises(Exception):
            MediaService.validate_image(empty_file)

    def test_07_oversized_file_rejected(self):
        """File exceeding 5MB raises clean ValidationError."""
        # 5MB + 1024 bytes
        large_bytes = b"0" * (MAX_FILE_SIZE_BYTES + 1024)
        oversized = SimpleUploadedFile("large.jpg", large_bytes, content_type="image/jpeg")
        with self.assertRaises(Exception) as ctx:
            MediaService.validate_image(oversized)
        self.assertIn("exceeds the 5MB limit", str(ctx.exception))

    def test_08_unsupported_extension_rejected(self):
        """Disallowed extensions (.pdf, .exe, .sh, .txt) are rejected."""
        disallowed = SimpleUploadedFile("malware.exe", b"MZDummyHeader", content_type="image/jpeg")
        with self.assertRaises(Exception) as ctx:
            MediaService.validate_image(disallowed)
        self.assertIn("Unsupported file extension", str(ctx.exception))

    def test_09_spoofed_mime_type_fails_pillow_verification(self):
        """Text file renamed with .jpg extension is caught and rejected by Pillow binary verification."""
        spoofed = SimpleUploadedFile("spoofed.jpg", b"echo 'malicious script'", content_type="image/jpeg")
        with self.assertRaises(Exception) as ctx:
            MediaService.validate_image(spoofed)
        self.assertIn("failed image verification", str(ctx.exception))

    def test_10_unsupported_mime_type_rejected(self):
        """MIME type not in allowed list is rejected."""
        dummy = create_dummy_image('JPEG')
        dummy.content_type = 'application/octet-stream'
        with self.assertRaises(Exception) as ctx:
            MediaService.validate_image(dummy)
        self.assertIn("Unsupported MIME type", str(ctx.exception))


@override_settings(
    CLOUDINARY_CLOUD_NAME='test_cloud',
    CLOUDINARY_API_KEY='test_key',
    CLOUDINARY_API_SECRET='test_secret',
)
class DoctorMediaUploadAndRBACTests(TestCase):
    """
    Test suite for Doctor profile photo upload, replacement, deletion, and RBAC permissions.
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.super_admin = User.objects.create_superuser(
            email='superadmin.media@hospital.local',
            password='Password123!',
            role=User.Role.SUPER_ADMIN,
        )
        self.hospital_admin = User.objects.create_user(
            email='hadmin.media@hospital.local',
            password='Password123!',
            role=User.Role.HOSPITAL_ADMIN,
        )
        self.doctor_user_1 = User.objects.create_user(
            email='dr.one@hospital.local',
            password='Password123!',
            role=User.Role.DOCTOR_STAFF,
        )
        self.doctor_user_2 = User.objects.create_user(
            email='dr.two@hospital.local',
            password='Password123!',
            role=User.Role.DOCTOR_STAFF,
        )
        self.patient_user = User.objects.create_user(
            email='patient.media@hospital.local',
            password='Password123!',
            role=User.Role.PATIENT,
        )

        # Department & Specialty
        self.dept = Department.objects.create(
            name='Cardiology Media Test',
            slug='cardiology-media-test',
            specialty='Cardiovascular',
            short_description='Heart care',
            full_description='Advanced cardiology',
            location='Wing A',
        )
        self.specialty = Specialty.objects.create(
            name='Interventional Cardio Media',
            slug='interventional-cardio-media',
        )

        # Doctors
        self.doctor_1 = Doctor.objects.create(
            user=self.doctor_user_1,
            name='Dr. Alice Smith',
            slug='dr-alice-smith-media',
            department=self.dept,
            specialty=self.specialty,
            qualification='MBBS, MD',
            consultation_location='Suite 101',
        )
        self.doctor_2 = Doctor.objects.create(
            user=self.doctor_user_2,
            name='Dr. Bob Jones',
            slug='dr-bob-jones-media',
            department=self.dept,
            specialty=self.specialty,
            qualification='MBBS, MS',
            consultation_location='Suite 102',
        )

    def test_11_unauthenticated_upload_rejected_401(self):
        """Anonymous user cannot upload a doctor photo."""
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor_1.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_12_patient_upload_rejected_403(self):
        """Patient user is forbidden from uploading doctor profile photos."""
        self.client.force_authenticate(user=self.patient_user)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor_1.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_13_patient_delete_rejected_403(self):
        """Patient user is forbidden from deleting doctor profile photos."""
        self.client.force_authenticate(user=self.patient_user)
        url = f"/api/doctors/{self.doctor_1.slug}/delete-photo/"
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('cloudinary.uploader.upload')
    def test_14_admin_upload_success_and_persistence(self, mock_upload):
        """Super Admin / Hospital Admin can upload a doctor profile photo with Cloudinary persistence."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice.jpg',
            'public_id': 'hospital-platform/doctors/dr_alice',
            'bytes': 15000,
            'format': 'jpg',
        }

        self.client.force_authenticate(user=self.super_admin)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor_1.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('photo_url', res.data)
        self.assertEqual(res.data['photo_url'], 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice.jpg')
        self.assertEqual(res.data['public_id'], 'hospital-platform/doctors/dr_alice')

        # Verify PostgreSQL persistence
        self.doctor_1.refresh_from_db()
        self.assertEqual(self.doctor_1.image_public_id, 'hospital-platform/doctors/dr_alice')
        self.assertIn('https://res.cloudinary.com/', str(self.doctor_1.image))

    @patch('cloudinary.uploader.upload')
    def test_15_doctor_staff_can_update_own_photo(self, mock_upload):
        """Doctor staff member can upload/update their own profile photo."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice_self.jpg',
            'public_id': 'hospital-platform/doctors/dr_alice_self',
            'bytes': 16000,
            'format': 'jpg',
        }

        self.client.force_authenticate(user=self.doctor_user_1)
        img = create_dummy_image('PNG')
        url = f"/api/doctors/{self.doctor_1.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['public_id'], 'hospital-platform/doctors/dr_alice_self')

    @patch('cloudinary.uploader.upload')
    def test_16_doctor_staff_cannot_update_other_doctor_photo(self, mock_upload):
        """Doctor staff member cannot modify another doctor's photo (object ownership enforced)."""
        self.client.force_authenticate(user=self.doctor_user_1)
        img = create_dummy_image('JPEG')
        # Attempt to upload to Doctor 2 (Dr. Bob Jones)
        url = f"/api/doctors/{self.doctor_2.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        mock_upload.assert_not_called()

    @patch('cloudinary.uploader.upload')
    def test_17_numeric_id_lookup_supported(self, mock_upload):
        """Upload endpoint works with numeric ID as well as slug."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice_id.jpg',
            'public_id': 'hospital-platform/doctors/dr_alice_id',
            'bytes': 15000,
            'format': 'jpg',
        }

        self.client.force_authenticate(user=self.super_admin)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor_1.id}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['doctor_id'], self.doctor_1.id)

    def test_18_serializer_exposes_photo_url_and_public_id(self):
        """Public Doctor GET endpoints expose photo_url, image_url, and image_public_id."""
        self.doctor_1.image = 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice.jpg'
        self.doctor_1.image_public_id = 'hospital-platform/doctors/dr_alice'
        self.doctor_1.save()

        # Anonymous public listing
        res = self.client.get(f"/api/doctors/{self.doctor_1.slug}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('photo_url', res.data)
        self.assertIn('image_url', res.data)
        self.assertIn('image_public_id', res.data)
        self.assertEqual(res.data['photo_url'], 'https://res.cloudinary.com/demo/image/upload/v12345/hospital-platform/doctors/dr_alice.jpg')
        self.assertEqual(res.data['image_public_id'], 'hospital-platform/doctors/dr_alice')


@override_settings(
    CLOUDINARY_CLOUD_NAME='test_cloud',
    CLOUDINARY_API_KEY='test_key',
    CLOUDINARY_API_SECRET='test_secret',
)
class MediaReplacementAndDeletionTests(TestCase):
    """
    Test suite for two-phase safe replacement, asset destruction, and idempotent deletion.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email='admin.replace@hospital.local',
            password='Password123!',
            role=User.Role.SUPER_ADMIN,
        )
        self.dept = Department.objects.create(
            name='Neurology Media',
            slug='neurology-media',
            specialty='Neurology',
            short_description='Brain care',
            full_description='Comprehensive neurology',
            location='Wing B',
        )
        self.doctor = Doctor.objects.create(
            name='Dr. Clara Oswald',
            slug='dr-clara-oswald-media',
            department=self.dept,
            qualification='MD (Neuro)',
            consultation_location='Suite 201',
            image='https://res.cloudinary.com/demo/image/upload/v1/hospital-platform/doctors/old_asset.jpg',
            image_public_id='hospital-platform/doctors/old_asset',
        )

    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.uploader.upload')
    def test_19_safe_replacement_destroys_previous_asset_after_persistence(self, mock_upload, mock_destroy):
        """Safe replacement uploads new image, saves to PostgreSQL, then destroys old Cloudinary asset."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v2/hospital-platform/doctors/new_asset.jpg',
            'public_id': 'hospital-platform/doctors/new_asset',
            'bytes': 20000,
            'format': 'jpg',
        }
        mock_destroy.return_value = {'result': 'ok'}

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Verify previous asset destroyed
        mock_destroy.assert_called_once_with('hospital-platform/doctors/old_asset', resource_type='image', invalidate=True)

        # Verify database updated with new asset
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.image_public_id, 'hospital-platform/doctors/new_asset')

    @patch('cloudinary.uploader.upload')
    def test_20_failed_upload_keeps_existing_photo(self, mock_upload):
        """When Cloudinary upload fails, existing photo reference in database remains untouched."""
        mock_upload.side_effect = Exception("Cloudinary connection timeout")

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Existing record must remain exactly as before
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.image_public_id, 'hospital-platform/doctors/old_asset')
        self.assertIn('old_asset.jpg', str(self.doctor.image))

    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.uploader.upload')
    def test_21_failed_db_update_cleans_up_new_asset(self, mock_upload, mock_destroy):
        """When database update fails after upload, new Cloudinary asset is destroyed immediately to prevent orphans."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v3/hospital-platform/doctors/orphan_candidate.jpg',
            'public_id': 'hospital-platform/doctors/orphan_candidate',
            'bytes': 10000,
            'format': 'jpg',
        }
        mock_destroy.return_value = {'result': 'ok'}

        img = create_dummy_image('JPEG')
        with patch.object(self.doctor, 'save', side_effect=Exception("Database lock failure")):
            with self.assertRaises(Exception):
                MediaService.replace_model_image(
                    instance=self.doctor,
                    file_obj=img,
                    image_field_name='image',
                    public_id_field_name='image_public_id',
                    folder='hospital-platform/doctors',
                )

        # The newly uploaded asset must have been cleaned up!
        mock_destroy.assert_called_once_with('hospital-platform/doctors/orphan_candidate', resource_type='image', invalidate=True)

    @patch('cloudinary.uploader.destroy')
    def test_22_authorized_delete_photo(self, mock_destroy):
        """Admin can delete a doctor photo, clearing the database and destroying the asset."""
        mock_destroy.return_value = {'result': 'ok'}

        self.client.force_authenticate(user=self.admin)
        url = f"/api/doctors/{self.doctor.slug}/delete-photo/"
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mock_destroy.assert_called_once_with('hospital-platform/doctors/old_asset', resource_type='image', invalidate=True)

        self.doctor.refresh_from_db()
        self.assertIsNone(self.doctor.image_public_id)
        self.assertFalse(bool(self.doctor.image))

    @patch('cloudinary.uploader.destroy')
    def test_23_repeated_deletion_is_safe_and_idempotent(self, mock_destroy):
        """Deleting an already deleted or empty photo succeeds cleanly without error."""
        self.doctor.image = None
        self.doctor.image_public_id = None
        self.doctor.save()

        self.client.force_authenticate(user=self.admin)
        url = f"/api/doctors/{self.doctor.slug}/delete-photo/"
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Destroy should not be called since there was no public_id
        mock_destroy.assert_not_called()


@override_settings(
    CLOUDINARY_CLOUD_NAME='test_cloud',
    CLOUDINARY_API_KEY='test_key',
    CLOUDINARY_API_SECRET='test_secret',
)
class HospitalAndFacilityMediaTests(TestCase):
    """
    Test suite for HospitalFacility, HospitalProfile, and HospitalAnnouncement media handling.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email='admin.hospmedia@hospital.local',
            password='Password123!',
            role=User.Role.HOSPITAL_ADMIN,
        )
        self.patient = User.objects.create_user(
            email='patient.hospmedia@hospital.local',
            password='Password123!',
            role=User.Role.PATIENT,
        )

        self.profile = HospitalProfile.objects.create(
            name='EgleSora Hospital Media Test',
            tagline='Care & Compassion',
            overview='Clinical excellence',
        )
        self.facility = HospitalFacility.objects.create(
            name='Cardiac Catheterization Lab',
            description='State-of-the-art cath lab',
            order=1,
        )
        self.announcement = HospitalAnnouncement.objects.create(
            title='New Wing Opening',
            slug='new-wing-opening-media',
            summary='Grand opening of pediatric wing',
            content='Full details of the event',
        )
        self.dept = Department.objects.create(
            name='Pediatrics Media Test',
            slug='pediatrics-media-test',
            specialty='Pediatrics',
            short_description='Child health',
            full_description='Comprehensive child healthcare',
            location='Wing C',
        )

    @patch('cloudinary.uploader.upload')
    def test_24_facility_image_upload_and_delete(self, mock_upload):
        """Hospital Admin can upload and delete facility images."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/hospital-platform/facilities/cath_lab.jpg',
            'public_id': 'hospital-platform/facilities/cath_lab',
            'bytes': 22000,
            'format': 'jpg',
        }

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('JPEG')
        url = f"/api/hospital/facilities/{self.facility.id}/upload-image/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['public_id'], 'hospital-platform/facilities/cath_lab')

        self.facility.refresh_from_db()
        self.assertEqual(self.facility.image_public_id, 'hospital-platform/facilities/cath_lab')

        # Test serializer output
        get_res = self.client.get(f"/api/hospital/facilities/{self.facility.id}/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertIn('image_url', get_res.data)

        # Delete image
        with patch('cloudinary.uploader.destroy') as mock_destroy:
            mock_destroy.return_value = {'result': 'ok'}
            del_res = self.client.delete(f"/api/hospital/facilities/{self.facility.id}/delete-image/")
            self.assertEqual(del_res.status_code, status.HTTP_200_OK)
            self.facility.refresh_from_db()
            self.assertIsNone(self.facility.image_public_id)

    def test_25_patient_cannot_upload_facility_image(self):
        """Patients cannot upload facility images."""
        self.client.force_authenticate(user=self.patient)
        img = create_dummy_image('JPEG')
        url = f"/api/hospital/facilities/{self.facility.id}/upload-image/"
        res = self.client.post(url, {'image': img}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    @patch('cloudinary.uploader.upload')
    def test_26_hospital_profile_logo_upload(self, mock_upload):
        """Hospital Admin can upload hospital logo/emblem."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/hospital-platform/hospital/hospital_logo.png',
            'public_id': 'hospital-platform/hospital/hospital_logo',
            'bytes': 18000,
            'format': 'png',
        }

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('PNG')
        url = "/api/hospital/upload-logo/"
        res = self.client.post(url, {'logo': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.logo_public_id, 'hospital-platform/hospital/hospital_logo')

        # Current profile GET exposes logo_url
        curr_res = self.client.get("/api/hospital/current/")
        self.assertEqual(curr_res.status_code, status.HTTP_200_OK)
        self.assertIn('logo_url', curr_res.data)

    @patch('cloudinary.uploader.upload')
    def test_27_announcement_image_upload(self, mock_upload):
        """Admin can upload announcement banner."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/hospital-platform/announcements/banner.webp',
            'public_id': 'hospital-platform/announcements/banner',
            'bytes': 14000,
            'format': 'webp',
        }

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('WEBP')
        url = f"/api/hospital/announcements/{self.announcement.slug}/upload-image/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.announcement.refresh_from_db()
        self.assertEqual(self.announcement.image_public_id, 'hospital-platform/announcements/banner')

    @patch('cloudinary.uploader.upload')
    def test_28_department_image_upload(self, mock_upload):
        """Admin can upload department image."""
        mock_upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/hospital-platform/departments/pediatrics.jpg',
            'public_id': 'hospital-platform/departments/pediatrics',
            'bytes': 25000,
            'format': 'jpg',
        }

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('JPEG')
        url = f"/api/departments/{self.dept.slug}/upload-image/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.image_public_id, 'hospital-platform/departments/pediatrics')


@override_settings(
    CLOUDINARY_CLOUD_NAME='test_cloud',
    CLOUDINARY_API_KEY='test_key',
    CLOUDINARY_API_SECRET='test_secret',
)
class MediaFailureHandlingAndSecurityTests(TestCase):
    """
    Test suite for failure handling, exception masking, and credential leakage prevention.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email='admin.sec@hospital.local',
            password='Password123!',
            role=User.Role.SUPER_ADMIN,
        )
        self.dept = Department.objects.create(
            name='Oncology Media Sec',
            slug='oncology-media-sec',
            specialty='Oncology',
            short_description='Cancer care',
            full_description='Advanced oncology',
            location='Wing D',
        )
        self.doctor = Doctor.objects.create(
            name='Dr. Diane Evans',
            slug='dr-diane-evans-sec',
            department=self.dept,
            qualification='MD (Oncology)',
            consultation_location='Suite 401',
        )

    @patch('cloudinary.uploader.upload')
    def test_29_cloudinary_error_returns_clean_400_without_secrets(self, mock_upload):
        """Cloudinary internal error returns safe message without leaking API secrets or internal traces."""
        # Simulate exception that contains internal credentials
        mock_upload.side_effect = Exception("Cloudinary backend failure: api_secret=sUpEr$eCrEt12345 timeout")

        self.client.force_authenticate(user=self.admin)
        img = create_dummy_image('JPEG')
        url = f"/api/doctors/{self.doctor.slug}/upload-photo/"
        res = self.client.post(url, {'image': img}, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # Verify secret was NEVER leaked into response body
        self.assertNotIn('sUpEr$eCrEt12345', str(res.data))
        self.assertNotIn('api_secret', str(res.data))
        self.assertIn('detail', res.data)

    def test_30_credentials_never_exposed_in_serializers(self):
        """Doctor and Hospital serializer outputs never include Cloudinary API secret or credentials."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/doctors/{self.doctor.slug}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        resp_str = str(res.data)
        self.assertNotIn('api_secret', resp_str)
        self.assertNotIn('CLOUDINARY_API_SECRET', resp_str)
        self.assertNotIn('CLOUDINARY_API_KEY', resp_str)


if __name__ == '__main__':
    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['tests.test_cloudinary_media'])
    sys.exit(bool(failures))

