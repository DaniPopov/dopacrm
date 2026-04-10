# TODO

## In Progress

*(nothing right now)*

## Backlog

### Features
- [ ] Tenant CRUD: add `saas_plan_id` FK when SaaS Plans table is built
- [ ] SaaS Plans CRUD (DopaCRM pricing tiers — Free/Starter/Pro)
- [ ] Members CRUD (gym customers — profiles, status, custom fields)
- [ ] Membership Plans CRUD (what the gym sells — monthly, annual, drop-in)
- [ ] Subscriptions (member ↔ plan assignment)
- [ ] Payments (recorded income events)
- [ ] Leads pipeline (capture → contacted → trial → converted/lost)
- [ ] Dashboard API (metrics: MRR, active members, churn, leads)
- [ ] Refresh tokens (POST /auth/refresh, POST /auth/logout, revoke in DB)
- [ ] Google OAuth login
- [ ] Microsoft OAuth login
- [ ] Password reset flow (email link → reset form)
- [ ] Nginx reverse proxy + load balancer

### Security / Hardening — Users
- [ ] Test PATCH with SQL injection in field values (`role = "'; DROP TABLE users; --"`)
- [ ] Test PATCH with invalid role value (not in enum)
- [ ] Test DELETE with someone else's user_id (owner from tenant A deleting tenant B user)
- [ ] Test creating user with extremely long email (buffer overflow attempt)
- [ ] Test creating user with null bytes in email (`\x00`)
- [ ] Test expired JWT returns 401
- [ ] Test rate limit actually blocks after 10 login attempts
- [ ] Test IDOR: regular user trying to access another user's profile

### Security / Hardening — Tenants
- [ ] Test PATCH with SQL injection in field values (`name = "'; DROP TABLE tenants; --"`)
- [ ] Test PATCH with invalid status value (not in enum — should reject)
- [ ] Test update with slug change to existing slug (should 409)
- [ ] Test creating tenant with extremely long slug (boundary test)
- [ ] Test creating tenant with null bytes in slug (`\x00`)
- [ ] Test creating tenant with special characters in slug (spaces, unicode)
- [ ] Test suspended tenant's users cannot log in (middleware enforcement — not yet built)
- [ ] Test owner trying to reactivate their own suspended tenant (must fail)
- [ ] Test staff trying to read tenant list via direct URL (must 403)
- [ ] Test IDOR: authenticated user from tenant A reading tenant B details
- [ ] Test mass enumeration: listing tenants with large offset to discover tenant count
- [ ] Test concurrent duplicate slug creation (race condition)
- [ ] Test update tenant_id in user PATCH (should not allow tenant transfer via PATCH)

### Security / Hardening — General
- [ ] X-Forwarded-For validation (trust only nginx proxy, reject spoofed headers)
- [ ] Bump password complexity (12+ chars, digits required) before first paying customer
- [ ] Add CORS preflight test
- [ ] Test OPTIONS requests don't leak information
- [ ] Add security headers (X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security)

### Infrastructure
- [ ] Nginx as reverse proxy (defer until backend scaling needed)
- [ ] Staging environment (defer until first paying customer)
- [ ] cAdvisor + Prometheus (defer until staging/prod with real traffic)
- [ ] Integration tests in CI (needs Postgres service in GitHub Actions)

## Done

- [x] Project scaffold (FastAPI, Docker Compose, CI, pre-commit)
- [x] Postgres: ORM models, Alembic migrations, per-entity folder layout
- [x] Domain: User entity, Role enum, Tenant entity, TenantStatus enum, AppError exceptions
- [x] Auth: JWT (PyJWT HS256), argon2 password hashing, HTTPBearer
- [x] API: v1/auth (login, me) + v1/users (CRUD) + v1/tenants (CRUD + suspend)
- [x] Service layer: UserService + TenantService with permission checks
- [x] Rate limiting: Redis-backed, 10/min/IP on login, 60/min/user on API
- [x] Rate limiter graceful degradation (fail-open if Redis is down)
- [x] Structured logging: structlog → Promtail → Loki → Grafana
- [x] Observability: Grafana dashboards, RabbitMQ Management, Flower
- [x] Celery: worker + worker-beat containers, 4 queues configured
- [x] Resource limits: t3.medium budget (2 vCPU, 4 GB)
- [x] Dockerfile: non-root user, uv, python:3.13-slim
- [x] Frontend: React + TypeScript + Vite + shadcn/ui (login + dashboard shell)
- [x] Tests: 64 total (unit + integration + E2E with security checks)
- [x] Security: SQL injection, XSS, JWT tampering, role escalation, tenant isolation
- [x] Tenant expand: status enum, timezone, currency, locale (Israel defaults)
- [x] Rename: company → tenant, roles (admin→owner, manager→staff, worker→sales)
- [x] CORS configured (dev origins whitelist, prod domain)
- [x] Password complexity (min 8, 1 uppercase, 1 special char)
- [x] Load testing: Locust (auth + users scenarios)
- [x] Seed script: create_super_admin via Make target
- [x] Docs: CLAUDE.md, README, specs.md, feature docs (users, auth, tenants), standards
