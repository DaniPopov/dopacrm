# Post-mortem: GET /api/v1/tenants/{id} leaked tenant data across tenants

**Date discovered:** 2026-04-17
**Date fixed:** 2026-04-17 (same day, caught pre-production)
**Severity:** High — a tenant owner could read any other tenant's name,
slug, contact info, billing status, and logo URL just by knowing or
guessing the UUID. Not a mutation leak, but a complete data-exposure
leak for the tenants table.
**Bug lived:** From tenant feature ship until this day (weeks).
**Exposed in prod:** No — dev-only DB, no live customers.

---

## What was wrong

The route `GET /api/v1/tenants/{tenant_id}` was authenticated (required
any valid JWT) but **not authorized by tenant**. Any logged-in user —
owner, staff, sales, or super_admin — could fetch any tenant's record.

Concretely:
- Owner of tenant A with JWT A → `GET /api/v1/tenants/<B-id>` → 200 OK,
  returns B's name, slug, contact info, billing status, logo URL.
- Staff and sales had the same capability (they just usually wouldn't
  know another tenant's UUID — but once someone did, all staff in all
  gyms could read each other's records).

## Root cause

The service method was written in a way that LOOKED scoped but wasn't:

```python
# BEFORE (buggy):
async def get_tenant(self, tenant_id: UUID) -> Tenant:
    """Get a single tenant by ID."""
    return await self._get_or_raise(tenant_id)
```

And the route:

```python
async def get_tenant(
    tenant_id: UUID,
    _caller: TokenPayload = Depends(get_current_user),  # named _caller
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.get_tenant(tenant_id)        # caller not passed!
    return _to_response(tenant)
```

Two red flags in that snippet:

1. The route dependency is named **`_caller`** with a leading underscore —
   a Python convention for "intentionally unused". This is fine for
   gating endpoints where any authenticated user is allowed (e.g., a
   health check). It is NOT fine for reads of a tenant-scoped resource.
2. `service.get_tenant(tenant_id)` doesn't take a caller. The signature
   itself says "nobody is being checked."

The combination made the leak invisible in review: an endpoint that
required authentication, with a service method that "looked sensible."
No `tenant_id` mismatch was ever raised because no mismatch was ever
checked.

## How we found it

We did NOT find this by reading the code. We found it by writing a
**consolidated cross-tenant isolation test suite** — one file that
probes every gym-scoped endpoint from a foreign tenant's token and
asserts 404 on each.

The test that caught it:

```python
def test_owner_cannot_read_foreign_tenant(client, two_gyms):
    r = client.get(
        f"/api/v1/tenants/{two_gyms['b']['tenant_id']}",
        headers=two_gyms["a"]["owner_headers"],
    )
    assert r.status_code in (403, 404)
```

The test was written mechanically — for every endpoint that takes an
`{id}` path parameter, write a test that hits it with the other
tenant's id. 31 of 32 tests passed on first run. This one failed with
`200`. That's how the bug surfaced.

The point: the test was written based on the **invariant** ("A can't
read B's tenant"), not based on reading `tenant_service.py`. If we had
tried to audit the code instead, the same two red flags above would
have looked like "a helper function" rather than a leak.

### Tactics that worked

1. **Write the invariant, not the implementation.** The test says
   "owner A cannot read tenant B" — a fact about the system. Not
   "TenantService.get_tenant checks caller" — a fact about the code.
2. **Consolidate into one suite.** If every feature's isolation
   tests were scattered, the missing one would be invisible. In a
   single file, a gap (no test for `GET /tenants/{id}`) is obvious.
3. **Seed two tenants, probe from one.** Not "unit-test the service
   with a wrong caller" — full HTTP round-trip, real JWT, real DB.
   That's the only level where this bug was observable.

## The fix

One-line-of-logic change at the service layer:

```python
# AFTER:
async def get_tenant(self, *, caller: TokenPayload, tenant_id: UUID) -> Tenant:
    tenant = await self._get_or_raise(tenant_id)
    if caller.role == Role.SUPER_ADMIN.value:
        return tenant
    if caller.tenant_id is None or str(caller.tenant_id) != str(tenant_id):
        raise TenantNotFoundError(str(tenant_id))  # 404, not 403
    return tenant
```

And the route now passes the caller:

```python
async def get_tenant(
    tenant_id: UUID,
    caller: TokenPayload = Depends(get_current_user),   # no underscore
    service: TenantService = Depends(_get_service),
) -> TenantResponse:
    tenant = await service.get_tenant(caller=caller, tenant_id=tenant_id)
    return _to_response(tenant)
```

Why 404 and not 403: 403 leaks the existence of the resource. If we
returned 403 for "tenant exists but isn't yours" and 404 for "tenant
doesn't exist", an attacker could probe the space of UUIDs to
enumerate which ones point at real tenants. 404 for both cases makes
the two states indistinguishable.

Why `super_admin` bypasses the check: super admin is the platform
support role. They see all tenants — that's the definition of the role.
This is documented in `docs/spec.md` and `docs/standards/architecture.md`.

## Process changes from this

1. **Service methods returning tenant-scoped resources MUST take
   `caller`.** Code-review flag: any service method named
   `get_*`, `list_*`, or `find_*` that returns a row with a
   `tenant_id` column and doesn't take a `caller` parameter is
   suspicious.
2. **Route handlers MUST NOT underscore the `caller` dependency.** An
   underscore tells the reader "this is intentionally unused." For
   tenant-scoped endpoints, the caller is NEVER unused — it's the
   thing that determines authorization.
3. **Every new feature adds its endpoints to
   `test_cross_tenant_isolation.py` in the same PR.** Not later.
   The review checklist now asks: "does this PR extend the isolation
   suite?"
4. **Before merging a tenant-scoped feature, grep for the service
   method in the routes and verify the `caller` is passed.**

## What we audited after the fix

After fixing the specific bug, we re-ran the full isolation suite plus
grepped for related patterns. Findings:

| Check | Result |
|---|---|
| All 32 tests in `test_cross_tenant_isolation.py` pass | ✓ |
| Other service methods that take `tenant_id` without `caller` | None found (grep confirmed) |
| Other routes using `_caller` naming | None in tenant-scoped endpoints |
| Repositories exposing `find_by_id` to routes directly | None — all go through services |

The pattern was unique to `get_tenant`. Other features (Members,
Classes, Plans, Subscriptions, Attendance) had the scoping check in
their service layers from day one.

## What we'd do differently

- This bug could have been caught by writing the isolation suite
  **when Tenants was originally shipped**, not now. Lesson: the
  isolation suite is not a follow-up feature. It's part of every
  tenant-scoped PR from day one.
- The name `_caller` in the route was a smell. A linter rule flagging
  underscored dependency parameters in auth-sensitive routes could
  catch this class of bug automatically. Future improvement — not
  urgent now that we have the test suite.

## Related

- Fix commit: (to be set at push time).
- Isolation suite: `backend/tests/e2e/test_cross_tenant_isolation.py`.
- Pattern doc: [`../cross-tenant-isolation.md`](../cross-tenant-isolation.md).
