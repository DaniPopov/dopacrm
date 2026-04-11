"""S3 client — singleton boto3 wrapper.

Lazy: the client is created on first call. Uses AWS credentials from app
settings (IAM user with scoped access to the DopaCRM bucket).

Env-based folder separation — every object is stored under:
    {env}/... → dev/..., staging/..., prod/...

So dev uploads never collide with prod data, and we can share a single
bucket across environments for cost savings. The env prefix is derived
from ``APP_ENV`` at runtime.

Objects inside the env prefix are organized by entity:
    dev/tenants/{tenant_id}/logo.png
    dev/members/{member_id}/avatar.jpg
    prod/tenants/{tenant_id}/logo.png
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import boto3

from app.core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@lru_cache
def get_s3_client() -> S3Client:
    """Return a cached boto3 S3 client bound to the configured region + credentials."""
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID.get_secret_value(),
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY.get_secret_value(),
    )


def get_env_prefix() -> str:
    """Return the environment folder prefix.

    Examples:
        development → ``dev``
        staging     → ``staging``
        production  → ``prod``
    """
    settings = get_settings()
    mapping = {
        "development": "dev",
        "staging": "staging",
        "production": "prod",
    }
    return mapping.get(settings.APP_ENV, "dev")


def build_key(path: str) -> str:
    """Prepend the environment prefix to an object key.

    Example:
        build_key("tenants/abc/logo.png") → "dev/tenants/abc/logo.png"
    """
    prefix = get_env_prefix()
    path = path.lstrip("/")
    return f"{prefix}/{path}"
