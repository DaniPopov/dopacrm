"""S3 storage adapter — private bucket with env-based folder separation.

Usage:
    from app.adapters.storage.s3 import upload_file, generate_presigned_url

    key = upload_file(
        file=upload.file,
        path=f"tenants/{tenant_id}/logo.png",
        content_type="image/png",
    )
    # → "dev/tenants/abc/logo.png"

    url = generate_presigned_url(key, expires_in=3600)
    # → "https://dopacrm-...s3.il-central-1.amazonaws.com/..."
"""

from app.adapters.storage.s3.client import build_key, get_env_prefix, get_s3_client
from app.adapters.storage.s3.storage import (
    delete_file,
    generate_presigned_url,
    upload_file,
)

__all__ = [
    "build_key",
    "delete_file",
    "generate_presigned_url",
    "get_env_prefix",
    "get_s3_client",
    "upload_file",
]
