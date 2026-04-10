# TODO

## In Progress

*(nothing right now)*

## Backlog

### Features
- [ ] Company CRUD API (v1/companies) — create, list, get, update, soft-delete
- [ ] Nginx reverse proxy + load balancer (for backend scaling / rolling restarts)
- [ ] Refresh tokens (POST /auth/refresh, POST /auth/logout, revoke in DB)
- [ ] Google OAuth login
- [ ] Microsoft OAuth login
- [ ] Password reset flow (email link → reset form)

### Security / Hardening
- [ ] Add more vulnerability tests to `backend/tests/e2e/test_users.py`:
  - [x] ~~Test JWT tampering (modify payload without re-signing)~~ → done
  - [x] ~~Test role escalation (worker→super_admin, manager→admin)~~ → done
  - [x] ~~Test admin with null company_id~~ → done
  - [ ] Test PATCH with SQL injection in field values (`role = "'; DROP TABLE users; --"`)
  - [ ] Test PATCH with invalid role value (not in enum)
  - [ ] Test DELETE with someone else's user_id (admin from company A deleting company B user)
  - [ ] Test creating user with extremely long email (buffer overflow attempt)
  - [ ] Test creating user with null bytes in email (`\x00`)
  - [ ] Test expired JWT returns 401
  - [ ] Test rate limit actually blocks after 10 login attempts
  - [ ] Test IDOR: regular user trying to access another user's profile
- [ ] X-Forwarded-For validation (trust only nginx proxy, reject spoofed headers)
- [ ] Bump password complexity (12+ chars, digits required) before first paying customer

### Infrastructure
- [ ] Nginx as reverse proxy (defer until backend scaling needed)
- [ ] Staging environment (defer until first paying customer)
- [ ] cAdvisor + Prometheus (defer until staging/prod with real traffic)
- [ ] Integration tests in CI (needs Postgres service in GitHub Actions)

## Done

- [x] Project scaffold (FastAPI, Docker Compose, CI, pre-commit)
- [x] Postgres: ORM models, Alembic migration, per-entity folder layout
- [x] Domain: User entity, Role enum, AppError exceptions
- [x] Auth: JWT (PyJWT HS256), argon2 password hashing, HTTPBearer
- [x] API: v1/auth (login, me) + v1/users (CRUD + list with company scoping)
- [x] Service layer: UserService with permission checks and business rules
- [x] Rate limiting: Redis-backed, 10/min/IP on login, 60/min/user on API
- [x] Rate limiter graceful degradation (fail-open if Redis is down)
- [x] Structured logging: structlog → Promtail → Loki → Grafana
- [x] Observability: Grafana dashboards, RabbitMQ Management, Flower
- [x] Celery: worker + worker-beat containers, 4 queues configured
- [x] Resource limits: t3.medium budget (2 vCPU, 4 GB)
- [x] Dockerfile: non-root user, uv, python:3.13-slim
- [x] Tests: 47 total (13 unit + 12 integration + 22 E2E)
- [x] Security: SQL injection, XSS, JWT tampering, role escalation, tenant isolation
- [x] Login tenant isolation fix (removed unsafe fallback query)
- [x] CORS configured (dev origins whitelist, prod domain)
- [x] Password complexity (min 8, 1 uppercase, 1 special char)
- [x] Load testing: Locust (auth + users scenarios)
- [x] Seed script: create_super_admin via Make target
- [x] Docs: CLAUDE.md, README, feature docs (users.md, auth.md), 4-layer guide, standards
