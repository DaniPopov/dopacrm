"""Request/response schemas for the Auth API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login"""

    email: EmailStr
    password: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "admin@dopacrm.com",
                    "password": "your-password",
                }
            ]
        }
    }


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "<jwt-token>",
                    "token_type": "bearer",
                    "expires_in": 28800,
                }
            ]
        }
    }
