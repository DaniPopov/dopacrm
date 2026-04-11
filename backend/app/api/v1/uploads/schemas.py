"""Request/response schemas for upload endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Response after a successful upload.

    ``key`` is the S3 object key (with env prefix, e.g. ``dev/tenants/.../logo.png``).
    Store this on the entity (e.g. ``tenants.logo_url``).

    ``presigned_url`` is a short-lived HTTPS URL the frontend can use to preview
    the file immediately without making a second request.
    """

    key: str = Field(description="Full S3 key including env prefix")
    presigned_url: str = Field(description="Short-lived URL for preview (1 hour)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "key": "dev/tenants/abc123/logo.png",
                    "presigned_url": "https://dopacrm-uploads-....s3.amazonaws.com/...",
                },
            ],
        },
    }
