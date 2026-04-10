# API Standards

> Conventions for all FastAPI endpoints in `app/api/`.

## URL Structure

```
/api/v1/{resource}
/api/v1/{resource}/{id}
/api/v1/{resource}/{id}/{sub-resource}
```

**Rules:**

- Always versioned (`v1`)
- Resource names are plural nouns: `/companies`, `/conversations`, `/residents`
- Use kebab-case for multi-word resources: `/company-contacts`
- IDs in path, filters in query params

**Examples:**

```
GET    /api/v1/conversations                    # List conversations for tenant
GET    /api/v1/conversations/{id}               # Get single conversation
POST   /api/v1/conversations/{id}/takeover      # Action on a resource
GET    /api/v1/companies/{id}/config             # Sub-resource
PUT    /api/v1/companies/{id}/config             # Update sub-resource
POST   /api/v1/auth/login                        # Auth (non-CRUD actions)
POST   /api/v1/auth/refresh                      # Token refresh
POST   /api/v1/webhooks/whatsapp                 # Webhook receiver
```

## HTTP Methods

| Method | Use |
|--------|-----|
| `GET` | Read (never mutates) |
| `POST` | Create resource or trigger action |
| `PUT` | Full update (replace entire resource) |
| `PATCH` | Partial update (update specific fields) |
| `DELETE` | Remove resource |

## Status Codes

| Code | When |
|------|------|
| `200` | Successful GET, PUT, PATCH, DELETE |
| `201` | Successful POST that creates a resource |
| `204` | Successful DELETE with no response body |
| `400` | Invalid request body / parameters |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but not authorized (wrong role, wrong tenant) |
| `404` | Resource not found |
| `409` | Conflict (duplicate slug, email already exists) |
| `422` | Pydantic validation failure (FastAPI default) |
| `429` | Rate limit exceeded |
| `500` | Unexpected server error |

## Request Schemas

Define in the route file or a dedicated `schemas.py` per route group. Separate from domain entities.

```python
# app/api/routes/companies.py

class CreateCompanyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=50)
    phone: str

class UpdateConfigRequest(BaseModel):
    agent: AgentConfigInput | None = None
    features: dict[str, bool] | None = None
    allowed_buildings: list[str] | None = None
```

**Rules:**

- Request models validate input — use Field constraints
- Request models may differ from domain entities (API exposes subset of fields)
- Use `| None` for optional fields in PATCH requests

## Response Format

All responses use a consistent envelope for list endpoints. Single-resource endpoints return the object directly.

### Single Resource

```json
{
  "id": "uuid-123",
  "name": "Acme Ltd.",
  "slug": "acme",
  "status": "active",
  "created_at": "2026-04-05T00:00:00Z"
}
```

### List / Collection

```json
{
  "data": [
    { "id": "uuid-123", "name": "Acme Ltd." },
    { "id": "uuid-456", "name": "Resolut" }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

### Response Models

```python
class CompanyResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, company: Company) -> "CompanyResponse":
        return cls(
            id=company.id,
            name=company.name,
            slug=company.slug,
            status=company.status,
            created_at=company.created_at,
        )

class PaginatedResponse[T](BaseModel):
    data: list[T]
    total: int
    page: int
    page_size: int
```

## Error Response Format

All errors follow the same shape:

```json
{
  "error": {
    "code": "COMPANY_NOT_FOUND",
    "message": "Company not found: uuid-123"
  }
}
```

**Implementation — global exception handler:**

```python
# app/api/error_handler.py

from app.domain.exceptions import AppError

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    status_map = {
        "COMPANY_NOT_FOUND": 404,
        "RESIDENT_NOT_VERIFIED": 403,
        "RATE_LIMIT_EXCEEDED": 429,
        "TENANT_SUSPENDED": 403,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, 500),
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

**Rules:**

- Never expose stack traces in production
- `code` is machine-readable (UPPER_SNAKE), `message` is human-readable
- Domain exceptions map to HTTP errors in the API layer — not in services

## Authentication

### Endpoints

```
POST /api/v1/auth/login          # Email + password → tokens
POST /api/v1/auth/login/google   # Google OAuth callback
POST /api/v1/auth/login/microsoft # Microsoft OAuth callback
POST /api/v1/auth/refresh        # Refresh token → new access token
POST /api/v1/auth/logout         # Revoke refresh token
```

### Tokens

| Token | Lifetime | Storage |
|-------|----------|---------|
| Access token (JWT) | 8 hours | httpOnly cookie |
| Refresh token | 30 days | httpOnly cookie + hash in Neon |

### JWT Payload

```json
{
  "sub": "user-uuid",
  "company_id": "company-uuid",
  "role": "admin",
  "exp": 1712000000,
  "iat": 1711971200
}
```

### Protected Routes

Use FastAPI dependency injection:

```python
# app/api/dependencies.py

async def get_tenant(
    token: str = Depends(oauth2_scheme),
) -> TenantContext:
    """Extract and validate JWT → return tenant context."""
    payload = decode_jwt(token)
    return TenantContext(
        user_id=payload["sub"],
        company_id=payload["company_id"],
        role=payload["role"],
    )

async def require_admin(tenant: TenantContext = Depends(get_tenant)) -> TenantContext:
    if tenant.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return tenant
```

Usage in routes:

```python
@router.get("/config")
async def get_config(tenant: TenantContext = Depends(get_tenant)):
    ...

@router.put("/config")
async def update_config(tenant: TenantContext = Depends(require_admin)):
    ...
```

## Pagination

For list endpoints — cursor-based or offset-based depending on the collection.

### Offset-based (default for dashboard queries)

```
GET /api/v1/conversations?page=1&page_size=20&status=ACTIVE
```

```python
class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
```

### Query Filtering

- Filters go in query params: `?status=ACTIVE&phone=972501234567`
- Date ranges: `?from=2026-04-01&to=2026-04-05`
- Sorting: `?sort_by=created_at&sort_order=desc`

## Webhook Endpoints

The WhatsApp webhook has different rules — it's called by Meta, not by our frontend.

```
GET  /api/v1/webhooks/whatsapp    # Verification challenge (Meta requires this)
POST /api/v1/webhooks/whatsapp    # Incoming messages
```

**Rules:**

- Validate webhook signature before processing (per-tenant secret)
- Return 200 immediately — push to queue, don't process inline
- No auth middleware on webhook routes (Meta can't send JWTs)
- Rate limit by source IP as additional protection

## API Versioning

- Version in URL path: `/api/v1/`
- When breaking changes are needed → create `/api/v2/` routes alongside v1
- Old version stays alive until all clients migrate
- Non-breaking additions (new optional fields, new endpoints) don't need a new version
