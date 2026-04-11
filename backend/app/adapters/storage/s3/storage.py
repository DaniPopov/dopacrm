"""S3 storage operations — upload, download, delete, presigned URLs.

Thin wrapper over boto3. All paths are automatically prefixed with the
environment folder (``dev/``, ``staging/``, ``prod/``) so different
environments never collide in the same bucket.

The bucket is **private** — files are served via presigned URLs that
expire after a configurable duration. Never make the bucket public.
"""

from __future__ import annotations

from typing import BinaryIO

from app.adapters.storage.s3.client import build_key, get_s3_client
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def upload_file(
    *,
    file: BinaryIO,
    path: str,
    content_type: str,
) -> str:
    """Upload a file to S3 under the env-prefixed path.

    Args:
        file: A file-like object (e.g. from FastAPI ``UploadFile.file``).
        path: The logical path WITHOUT env prefix (e.g. ``tenants/abc/logo.png``).
        content_type: MIME type (e.g. ``image/png``).

    Returns:
        The full S3 key (with env prefix), e.g. ``dev/tenants/abc/logo.png``.
    """
    settings = get_settings()
    key = build_key(path)
    client = get_s3_client()

    client.upload_fileobj(
        file,
        settings.AWS_S3_BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("s3_upload", key=key, content_type=content_type)
    return key


def delete_file(key: str) -> None:
    """Delete an object from S3.

    Args:
        key: The full S3 key (including env prefix).
    """
    settings = get_settings()
    client = get_s3_client()
    client.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
    logger.info("s3_delete", key=key)


def generate_presigned_url(key: str, *, expires_in: int = 3600) -> str:
    """Generate a time-limited URL to read a private S3 object.

    Args:
        key: The full S3 key (including env prefix).
        expires_in: Seconds until the URL expires. Default 1 hour.

    Returns:
        A presigned HTTPS URL the client can use to fetch the file.
    """
    settings = get_settings()
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
