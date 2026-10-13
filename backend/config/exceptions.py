"""
Custom Exception Handler for Hospital Platform REST API (Phase 16).
Provides safe error formatting, credential masking, and prevents internal
tracebacks or database details from leaking in HTTP 500 responses.
"""

import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Production-grade REST Framework exception handler.
    Guarantees:
    - Standard DRF error formats (400, 401, 403, 404, 409, 429)
    - Prevents stack traces, database schema details, and credentials from leaking in 500 errors
    - Strips internal secrets from error messages
    """
    # Call REST framework's default exception handler first to get the standard error response.
    response = exception_handler(exc, context)

    if response is not None:
        # Sanitize data to ensure no secret keys appear in error responses
        if isinstance(response.data, dict):
            cloudinary_secret = getattr(settings, 'CLOUDINARY_API_SECRET', '')
            django_secret = getattr(settings, 'SECRET_KEY', '')
            for k in list(response.data.keys()):
                val = response.data[k]
                if isinstance(val, str):
                    if cloudinary_secret and cloudinary_secret in val:
                        response.data[k] = val.replace(cloudinary_secret, '[REDACTED]')
                    if django_secret and django_secret in val:
                        response.data[k] = val.replace(django_secret, '[REDACTED]')
        return response

    # If response is None, an unhandled server error occurred (500)
    view_name = context.get('view').__class__.__name__ if context.get('view') else 'UnknownView'
    logger.error(
        f"[SERVER_ERROR] Unhandled exception in {view_name}: {exc}",
        exc_info=settings.DEBUG,
    )

    if settings.DEBUG:
        # In debug mode during local developer inspection, return standard exception details
        return Response(
            {"detail": f"Internal Server Error: {str(exc)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # In production (DEBUG=False), strictly return sanitized message with zero internal exposure
    return Response(
        {"detail": "An internal server error occurred. Please contact hospital support."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
