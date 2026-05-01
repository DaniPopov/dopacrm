# TODO

## In Progress

*(nothing right now)*

## Backlog

### Features — Core CRM (next up)
- [ ] Members CRUD (gym customers — profiles, status, custom fields)
- [ ] Membership Plans CRUD (what the gym sells — monthly, annual, drop-in)
- [ ] Subscriptions (member ↔ plan assignment)
- [ ] Payments (recorded income events)
- [ ] Leads pipeline (capture → contacted → trial → converted/lost)
- [ ] Dashboard: real metrics (replaces "בקרוב" placeholders in AdminDashboard/GymDashboard)

### Features — Flexibility (Phase 4 — after Core CRM)
- [ ] **Dynamic roles system** — `tenant_roles` table, owner creates/edits/deletes roles per tenant. Spec: `docs/features/roles.md`.
  - [ ] Backend: `tenant_roles` table + migration + seed defaults ("Staff", "Sales") on tenant creation
  - [ ] Backend: Role entity, RoleRepository, tenant_roles CRUD API (owner-scoped)
  - [ ] Backend: `users.role_id` FK replaces `users.role` text column
  - [ ] Backend: `/auth/me` returns role as object `{id, name, features, is_system}`
  - [ ] Frontend: `permissions.ts` — delete hardcoded BASELINE, read from `user.role.features` directly
  - [ ] Frontend: `/settings/roles` page — owner-only, CRUD with feature checkbox grid
  - [ ] Frontend: user form role dropdown pulls from `useRoles()` instead of hardcoded list
  - [ ] Frontend: prevent editing/deleting system roles (owner/super_admin)
- [ ] Custom fields UI for members (owner adds/renames fields in `members.custom_fields`)
- [ ] Custom attrs UI for membership plans (owner edits `membership_plans.custom_attrs`)
- [ ] Per-tenant dashboard widget layout (v2 — Postgres `user_dashboard_configs` table with JSONB layout)

### Mobile (deferred — see `docs/mobile-setup.md`)
- [ ] Decide trigger: 4-6 weeks after web CRM in prod, based on real-customer feedback
- [ ] Refactor: move `frontend/src/lib/api-{schema,types}.ts` into `packages/api-types/` workspace package
- [ ] Set up React Native + Expo project (TypeScript strict, EAS Build)
- [ ] v1 features: login, member search + check-in, member profile, add member, sell pass
- [ ] Push notifications: backend `user_push_tokens` table, Celery task for sends, Expo SDK on mobile
- [ ] Offline mode for check-in (v2, behind a flag)

### Features — Misc
- [ ] Tenant CRUD: add `saas_plan_id` FK when SaaS Plans table is built
- [ ] SaaS Plans CRUD (DopaCRM pricing tiers — Free/Starter/Pro)
- [ ] Users frontend: full CRUD page (currently placeholder)
- [ ] Refresh tokens (POST /auth/refresh — short-lived access + long-lived refresh)
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

### Security / Hardening — Auth
- [ ] Test blacklisted token can't access any endpoint (not just /me)
- [ ] Test Redis down → blacklist check skipped (fail-open)
- [ ] Test cookie not sent cross-origin (SameSite=Lax enforcement)
- [ ] Test expired cookie is rejected

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
- [x] Auth: JWT (PyJWT HS256), argon2 password hashing
- [x] Auth: HttpOnly cookie storage (XSS-immune, replaces localStorage)
- [x] Auth: Redis token blacklist on logout (jti-based, TTL = remaining expiry)
- [x] Auth: dual support — cookie (frontend) + Bearer header (Swagger/API clients)
- [x] Auth: POST /logout endpoint (clears cookie + blacklists token)
- [x] API: v1/auth (login, logout, me) + v1/users (CRUD) + v1/tenants (CRUD + suspend)
- [x] Service layer: UserService + TenantService with permission checks
- [x] Rate limiting: Redis-backed, 10/min/IP on login, 60/min/user on API
- [x] Rate limiter graceful degradation (fail-open if Redis is down)
- [x] Structured logging: structlog → Promtail → Loki → Grafana
- [x] Observability: Grafana dashboards, RabbitMQ Management, Flower
- [x] Celery: worker + worker-beat containers, 4 queues configured
- [x] Resource limits: t3.medium budget (2 vCPU, 4 GB)
- [x] Dockerfile: non-root user, uv, python:3.13-slim
- [x] Frontend: React + TypeScript + Vite + TanStack Query + shadcn/ui
- [x] Frontend: feature-based architecture (auth, tenants, dashboard, landing, users)
- [x] Frontend: Hebrew landing page with brand assets
- [x] Frontend: login page (split layout, password toggle, brand images)
- [x] Frontend: tenant management page (create, list, suspend — super_admin)
- [x] Frontend: RTL sidebar with declarative role-based nav + extracted `Sidebar` component
- [x] Frontend: AuthProvider + ProtectedRoute + DashboardLayout
- [x] Frontend: Hebrew dashboard — role dispatcher + AdminDashboard + GymDashboard + StatCard
- [x] Frontend: central `permissions.canAccess(user, feature)` module (ready for dynamic roles)
- [x] Frontend: `RequireFeature` route guard (URL-typing doesn't bypass sidebar)
- [x] Frontend: `User.role` typed as `Role` union instead of `string`
- [x] Tests: 89+ backend (unit + integration + E2E) + 34 frontend (Vitest)
- [x] Security: SQL injection, XSS, JWT tampering, role escalation, tenant isolation
- [x] Security: cookie auth tests, token blacklist after logout verified
- [x] Tenant expand: status enum, timezone, currency, locale (Israel defaults)
- [x] Rename: company → tenant, roles (admin→owner, manager→staff, worker→sales)
- [x] CORS configured (dev origins whitelist, prod domain)
- [x] Password complexity (min 8, 1 uppercase, 1 special char)
- [x] Load testing: Locust (auth, users, tenants scenarios)
- [x] Seed script: create_super_admin via Make target
- [x] Makefile: test targets (backend unit/integration/e2e/all, frontend, all)
- [x] CI: backend lint+test, frontend lint+test, gitleaks, pip-audit, docker build
- [x] Docs: CLAUDE.md, README, spec.md, backend.md, frontend.md, feature docs, standards
