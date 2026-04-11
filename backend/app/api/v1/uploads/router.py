"""Upload routes — ``/api/v1/uploads``.

Handles multipart file uploads for branding assets (logos, eventually
member photos, class thumbnails, etc.).

The backend accepts the file, validates size + content type, uploads to
S3 via the storage adapter, and returns the S3 key + a short-lived
presigned URL for immediate preview. The caller is responsible for
persisting the key (e.g. saving it on the tenant row).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.adapters.storage.s3 import generate_presigned_url, upload_file
from app.api.dependencies.auth import require_super_admin
from app.api.v1.uploads.schemas import UploadResponse
from app.core.logger import get_logger
from app.core.security import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

# Allowlisted image types — anything else is rejected at the API boundary
_ALLOWED_LOGO_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


@router.post(
    "/logo",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a tenant logo",
    description=(
        "Accepts PNG, JPEG, WebP, or SVG up to 2 MB. "
        "Returns the S3 key and a short-lived presigned URL. "
        "super_admin only — this is used during tenant onboarding."
    ),
)
async def upload_logo(
    file: UploadFile,
    _caller: TokenPayload = Depends(require_super_admin),
) -> UploadResponse:
    # Content-type check
    if file.content_type not in _ALLOWED_LOGO_TYPES:
        allowed = ", ".join(sorted(_ALLOWED_LOGO_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported logo content type. Allowed: {allowed}",
        )

    # Size check — read into memory up to the limit
    contents = await file.read()
    if len(contents) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Logo exceeds 2 MB (got {len(contents)} bytes)",
        )
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    # Put the bytes back into a fresh file-like object for boto3
    from io import BytesIO

    buf = BytesIO(contents)

    # Random UUID path — the tenant doesn't exist yet at upload time
    ext = _ALLOWED_LOGO_TYPES[file.content_type]
    upload_id = uuid4().hex
    key = upload_file(
        file=buf,
        path=f"tenants/{upload_id}/logo.{ext}",
        content_type=file.content_type,
    )

    preview_url = generate_presigned_url(key, expires_in=3600)
    logger.info(
        "logo_uploaded",
        key=key,
        size_bytes=len(contents),
        content_type=file.content_type,
    )
    return UploadResponse(key=key, presigned_url=preview_url)
