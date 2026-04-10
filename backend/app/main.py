import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handler import app_error_handler
from app.api.middleware import AccessLogMiddleware
from app.api.v1.router import v1_router
from app.core.logger import setup_logging
from app.domain.exceptions import AppError

setup_logging()

_is_production = os.getenv("APP_ENV", "development") == "production"

# Allowed origins — React dev servers in dev, real domain in prod.
_CORS_ORIGINS = (
    ["https://app.dopacrm.com"]
    if _is_production
    else [
        "http://localhost:3000",  # React dev (Vite default)
        "http://localhost:5173",  # React dev (alt)
        "http://localhost:8000",  # Swagger UI
    ]
)

app = FastAPI(
    title="DopaCRM",
    description="Multi-tenant SaaS CRM for gyms and fitness studios",
    version="0.1.0",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessLogMiddleware)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(v1_router)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
