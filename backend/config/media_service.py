"""
Cloudinary Media Service & Image Validation Layer (Phase 15).

Provides production-ready media handling:
- Strict media validation (file size, MIME types, extensions, Pillow binary verification)
- Structured Cloudinary upload with folder paths and web optimizations
- Secure asset URL and public_id persistence in PostgreSQL domain models
- Two-phase safe media replacement (validate -> upload -> save DB -> destroy old asset)
- Safe idempotent media deletion
- Complete error isolation (credentials and internal provider traces never leaked)
"""

import os
import uuid
import logging
from io import BytesIO
from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError

logger = logging.getLogger('hospital.media')

# Production Media Constraints
ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
}

ALLOWED_EXTENSIONS = {
    '.jpg',
    '.jpeg',
    '.png',
    '.webp',
}

# 5 Megabytes limit appropriate for high-fidelity clinical and facility photography
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Standardized folder hierarchy for Cloudinary storage
CLOUDINARY_FOLDERS = {
    'doctors': 'hospital-platform/doctors',
    'facilities': 'hospital-platform/facilities',
    'hospital': 'hospital-platform/hospital',
    'announcements': 'hospital-platform/announcements',
    'departments': 'hospital-platform/departments',
}


class MediaService:
    """
    Central service for validating, uploading, replacing, and deleting
    Cloudinary-backed media assets across the Hospital Platform.
    """

    @classmethod
    def is_cloudinary_configured(cls) -> bool:
        """
        Check if valid Cloudinary credentials exist in environment settings.
        """
        cloud_name = getattr(settings, 'CLOUDINARY_CLOUD_NAME', '')
        api_key = getattr(settings, 'CLOUDINARY_API_KEY', '')
        api_secret = getattr(settings, 'CLOUDINARY_API_SECRET', '')
        return bool(cloud_name and api_key and api_secret)

    @classmethod
    def validate_image(cls, file_obj) -> None:
        """
        Perform strict security and integrity validation on an uploaded image file:
        1. File existence
        2. Maximum file size (5MB)
        3. Whitelisted file extensions (.jpg, .jpeg, .png, .webp)
        4. Whitelisted MIME types
        5. Binary content inspection via Pillow to reject corrupted files, scripts, or executables
        """
        if not file_obj:
            raise ValidationError({"file": ["No media file provided."]})

        # 1. Size check
        file_size = getattr(file_obj, 'size', None)
        if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValidationError({
                "file": [f"File size exceeds the {max_mb}MB limit. Uploaded size: {file_size} bytes."]
            })

        # 2. Extension check
        filename = getattr(file_obj, 'name', '') or ''
        ext = os.path.splitext(filename)[1].lower()
        if not ext or ext not in ALLOWED_EXTENSIONS:
            allowed_str = ', '.join(sorted(ALLOWED_EXTENSIONS))
            raise ValidationError({
                "file": [f"Unsupported file extension '{ext}'. Allowed extensions: {allowed_str}."]
            })

        # 3. MIME type check
        content_type = getattr(file_obj, 'content_type', None)
        if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
            allowed_mimes = ', '.join(sorted(ALLOWED_MIME_TYPES))
            raise ValidationError({
                "file": [f"Unsupported MIME type '{content_type}'. Allowed types: {allowed_mimes}."]
            })

        # 4. Binary inspection via Pillow Image.open() & verify()
        try:
            from PIL import Image
            file_obj.seek(0)
            # Read first chunk or entire buffer into BytesIO
            content = file_obj.read()
            if not content:
                raise ValidationError({"file": ["Uploaded file is empty."]})

            buffer = BytesIO(content)
            img = Image.open(buffer)
            img.verify()

            # Confirm format matches allowed set
            img_format = (img.format or '').upper()
            if img_format not in ['JPEG', 'PNG', 'WEBP']:
                raise ValidationError({
                    "file": [f"Decoded image format '{img_format}' is not an authorized web image format."]
                })

            # Reset file pointer for subsequent operations
            file_obj.seek(0)
        except Exception as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError({
                "file": [f"Uploaded file failed image verification: {str(exc)}"]
            })

    @classmethod
    def upload_image(
        cls,
        file_obj,
        folder: str = 'hospital-platform/doctors',
        public_id: str = None,
        transformation: list = None
    ) -> dict:
        """
        Uploads a validated image to Cloudinary (or local storage fallback if unconfigured).
        Returns a dict: {'url': secure_url, 'public_id': public_id, 'bytes': int, 'format': str}
        """
        cls.validate_image(file_obj)

        if cls.is_cloudinary_configured():
            try:
                import cloudinary
                import cloudinary.uploader

                cloudinary.config(
                    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                    api_key=settings.CLOUDINARY_API_KEY,
                    api_secret=settings.CLOUDINARY_API_SECRET,
                    secure=True,
                )

                file_obj.seek(0)
                upload_params = {
                    'folder': folder,
                    'resource_type': 'image',
                    'secure': True,
                    'overwrite': True,
                }
                if public_id:
                    upload_params['public_id'] = public_id

                if transformation:
                    upload_params['transformation'] = transformation
                else:
                    upload_params['transformation'] = [
                        {'quality': 'auto', 'fetch_format': 'auto'}
                    ]

                result = cloudinary.uploader.upload(file_obj, **upload_params)
                secure_url = result.get('secure_url') or result.get('url')
                res_public_id = result.get('public_id')

                logger.info(f"[MEDIA_UPLOAD_SUCCESS] Uploaded {res_public_id} to folder {folder}")
                return {
                    'url': secure_url,
                    'public_id': res_public_id,
                    'bytes': result.get('bytes', 0),
                    'format': result.get('format', ''),
                }
            except Exception as exc:
                # Sanitized logging: never log API key or secret!
                clean_msg = str(exc).split(getattr(settings, 'CLOUDINARY_API_SECRET', 'NO_SECRET'))[0]
                logger.error(f"[MEDIA_UPLOAD_FAILED] Cloudinary error: {clean_msg}")
                raise ValidationError({
                    "detail": "Media upload service temporarily unavailable. Please try again."
                })
        else:
            # Fallback for offline testing or development environments without live credentials
            file_obj.seek(0)
            rand_token = uuid.uuid4().hex[:12]
            filename = f"{rand_token}_{getattr(file_obj, 'name', 'image.jpg')}"
            saved_path = default_storage.save(f"{folder}/{filename}", file_obj)
            url = default_storage.url(saved_path)
            simulated_public_id = f"{folder}/{rand_token}"

            logger.info(f"[MEDIA_FALLBACK_SAVED] Saved local storage fallback: {saved_path}")
            return {
                'url': url,
                'public_id': simulated_public_id,
                'bytes': getattr(file_obj, 'size', 0),
                'format': os.path.splitext(filename)[1].lstrip('.'),
            }

    @classmethod
    def delete_image(cls, public_id: str) -> bool:
        """
        Safely and idempotently destroys a Cloudinary image asset by its public ID.
        """
        if not public_id:
            return True

        if cls.is_cloudinary_configured():
            try:
                import cloudinary
                import cloudinary.uploader

                cloudinary.config(
                    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                    api_key=settings.CLOUDINARY_API_KEY,
                    api_secret=settings.CLOUDINARY_API_SECRET,
                    secure=True,
                )
                res = cloudinary.uploader.destroy(public_id, resource_type='image', invalidate=True)
                logger.info(f"[MEDIA_DELETE_SUCCESS] Destroyed asset {public_id}: result={res.get('result')}")
                return True
            except Exception as exc:
                clean_msg = str(exc).split(getattr(settings, 'CLOUDINARY_API_SECRET', 'NO_SECRET'))[0]
                logger.warning(f"[MEDIA_DELETE_FAILED] Could not destroy asset {public_id}: {clean_msg}")
                return False
        return True

    @classmethod
    def replace_model_image(
        cls,
        instance,
        file_obj,
        image_field_name: str = 'image',
        public_id_field_name: str = 'image_public_id',
        folder: str = 'hospital-platform/doctors'
    ) -> dict:
        """
        Atomically and safely replaces an existing model's image asset:
        1. Validate new image.
        2. Upload new image to Cloudinary.
        3. Confirm successful upload.
        4. Update database reference in PostgreSQL.
        5. Remove old Cloudinary asset only AFTER new asset reference is safely saved.
        If upload or DB save fails, existing image reference remains intact.
        """
        # Step 1 & 2: Validate and upload new image
        old_public_id = getattr(instance, public_id_field_name, None)
        upload_result = cls.upload_image(file_obj, folder=folder)

        # Step 3 & 4: Update database record
        setattr(instance, image_field_name, upload_result['url'])
        setattr(instance, public_id_field_name, upload_result['public_id'])

        try:
            update_fields = [image_field_name, public_id_field_name]
            if hasattr(instance, 'updated_at'):
                update_fields.append('updated_at')
            instance.save(update_fields=update_fields)
        except Exception as exc:
            # If database save fails, roll back Cloudinary asset to avoid orphan garbage
            cls.delete_image(upload_result['public_id'])
            logger.error(f"[MEDIA_REPLACE_DB_ERROR] Failed to save record {instance.pk}: {exc}")
            raise ValidationError({
                "detail": "Failed to update database record with uploaded media URL."
            })

        # Step 5: Safely release previous asset now that new asset is successfully persisted
        if old_public_id and old_public_id != upload_result['public_id']:
            cls.delete_image(old_public_id)

        return upload_result

    @classmethod
    def delete_model_image(
        cls,
        instance,
        image_field_name: str = 'image',
        public_id_field_name: str = 'image_public_id'
    ) -> bool:
        """
        Safely removes media asset reference from database and destroys Cloudinary asset.
        Idempotent: attempting to delete an already empty image asset succeeds cleanly.
        """
        old_public_id = getattr(instance, public_id_field_name, None)

        setattr(instance, image_field_name, None)
        setattr(instance, public_id_field_name, None)

        update_fields = [image_field_name, public_id_field_name]
        if hasattr(instance, 'updated_at'):
            update_fields.append('updated_at')
        instance.save(update_fields=update_fields)

        if old_public_id:
            cls.delete_image(old_public_id)

        return True
