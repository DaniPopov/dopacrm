"""E2E tests for upload endpoints.

S3 calls are mocked so tests run without real AWS credentials.
A separate manual smoke test (not in pytest) verifies the real S3 path.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

# Tiny valid 1x1 PNG (minimum valid PNG bytes)
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
    "ae426082",
)


def test_upload_logo_success(client: TestClient, auth_headers: dict) -> None:
    with (
        patch("app.api.v1.uploads.router.upload_file") as mock_upload,
        patch("app.api.v1.uploads.router.generate_presigned_url") as mock_presign,
    ):
        mock_upload.return_value = "dev/tenants/abc123/logo.png"
        mock_presign.return_value = "https://fake-s3.example.com/signed-url"

        resp = client.post(
            "/api/v1/uploads/logo",
            headers=auth_headers,
            files={"file": ("logo.png", _TINY_PNG, "image/png")},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "dev/tenants/abc123/logo.png"
    assert data["presigned_url"] == "https://fake-s3.example.com/signed-url"

    # Verify upload_file was called with correct args
    assert mock_upload.call_count == 1
    call_kwargs = mock_upload.call_args.kwargs
    assert call_kwargs["content_type"] == "image/png"
    assert call_kwargs["path"].startswith("tenants/")
    assert call_kwargs["path"].endswith("/logo.png")


def test_upload_logo_accepts_jpeg(client: TestClient, auth_headers: dict) -> None:
    with (
        patch("app.api.v1.uploads.router.upload_file") as mock_upload,
        patch("app.api.v1.uploads.router.generate_presigned_url") as mock_presign,
    ):
        mock_upload.return_value = "dev/tenants/xyz/logo.jpg"
        mock_presign.return_value = "https://fake/url"

        resp = client.post(
            "/api/v1/uploads/logo",
            headers=auth_headers,
            files={"file": ("photo.jpg", b"\xff\xd8\xff" + b"\x00" * 100, "image/jpeg")},
        )
    assert resp.status_code == 201
    assert resp.json()["key"].endswith(".jpg")


def test_upload_logo_rejects_wrong_content_type(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/uploads/logo",
        headers=auth_headers,
        files={"file": ("logo.exe", b"MZ" + b"\x00" * 100, "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert "Unsupported" in resp.json()["detail"]


def test_upload_logo_rejects_empty_file(client: TestClient, auth_headers: dict) -> None:
    resp = client.post(
        "/api/v1/uploads/logo",
        headers=auth_headers,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 400
    assert "Empty" in resp.json()["detail"]


def test_upload_logo_rejects_oversized(client: TestClient, auth_headers: dict) -> None:
    # 3 MB of junk with an image content type
    big = b"\x00" * (3 * 1024 * 1024)
    resp = client.post(
        "/api/v1/uploads/logo",
        headers=auth_headers,
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 413
    assert "2 MB" in resp.json()["detail"]


def test_upload_logo_requires_super_admin(client: TestClient) -> None:
    """Without auth → 401/403."""
    resp = client.post(
        "/api/v1/uploads/logo",
        files={"file": ("logo.png", _TINY_PNG, "image/png")},
    )
    assert resp.status_code in (401, 403)
