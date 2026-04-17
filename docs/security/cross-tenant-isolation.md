# Cross-tenant isolation — the core invariant

> **One rule:** staff / owner / sales in tenant A cannot read or mutate
> tenant B's data under any circumstance. Not via forged IDs, not via
> guessable URLs, not via API quirks. Not even error messages should
> confirm that a given resource exists in another tenant.

Every feature in DopaCRM lives under this rule. If you're adding a
new endpoint, new table, or new service method, the first question
is *"how does this stay tenant-scoped?"* — not an afterthought.

## The three layers of defense

Defense in depth. Each layer is narrow enough to reason about; together
they cover the gaps the others miss.

### Layer 1 — Service-level tenant scoping

**Every gym-scoped service method takes a `caller: TokenPayload` and
checks it.** Two patterns recur:

- **Read**: look up the resource by id, then compare
  `resource.tenant_id` to `caller.tenant_id`. If they don't match,
  raise `NotFoundError` (not 403 — we don't confirm existence).
  `super_admin` bypasses the check (platform support).

  ```python
  async def _get_in_tenant(self, caller, sub_id):
      sub = await self._repo.find_by_id(sub_id)
      if sub is None:
          raise SubscriptionNotFoundError(str(sub_id))
      if caller.role == Role.SUPER_ADMIN.value:
          return sub
      if caller.tenant_id is None or str(sub.tenant_id) != str(caller.tenant_id):
          raise SubscriptionNotFoundError(str(sub_id))  # 404, not 403
      return sub
  ```

- **List / write**: extract `caller.tenant_id` up front, pass it to the
  repo as the scoping filter. The repo never accepts a "list all"
  call from the service.

  ```python
  tenant_id = self._require_tenant(caller)
  return await self._repo.list_for_tenant(tenant_id, ...)
  ```

**Mistake to avoid:** passing `tenant_id` from the request body. Always
take it from the JWT, never from user input. Even if the body
happens to match the JWT, it's one typo away from a leak.

### Layer 2 — Repository-level tenant filter

Repositories should never offer a "get by id without tenant scope"
method that's intended for normal use. The `find_by_id(id)` helpers
exist so the service can check-then-scope (as above) — they're NOT
meant to be used from routes directly.

Periodically grep for `find_by_id\(` in the API layer. If a route
calls it directly, that's a bug.

### Layer 3 — Database FK + ORM model

The `tenant_id` column on every gym-scoped table has a CASCADE FK to
`tenants.id`. Delete a tenant, its data goes. Guarantees no orphan
rows outlive their tenant.

This layer doesn't prevent cross-tenant **reads** (the FK is for
referential integrity, not authorization). That's what Layer 1 is for.

## The test pattern

We maintain one consolidated suite:

**`backend/tests/e2e/test_cross_tenant_isolation.py`**

It seeds two tenants, A and B, each with a full set of resources
(member / class / plan / subscription / attendance entry / users). Then
it uses A's owner / staff / sales tokens to probe **every gym-scoped
endpoint** with B's IDs.

Expected results:
- GET / PATCH / POST-action on a foreign resource → **404**
  (not 403 — don't leak existence).
- Cross-tenant payloads on create endpoints (e.g., plan_id from B
  when enrolling one of A's members) → **422** with a typed error.
- List endpoints → return only A's resources, never B's.

**Rule for new features:** when you add an endpoint, you add the
cross-tenant probe to this file in the same PR. Not later.

### Why one consolidated file and not per-feature?

- **Consistency**: all endpoints get the same treatment — same fixture,
  same headers, same assertions.
- **Gap visibility**: a new endpoint that's NOT in this file is
  immediately obvious in review ("did you add the isolation test?").
- **Drift resistance**: if we change the seed-data helper, all
  isolation tests get the new invariant automatically.

### Anti-pattern: "it's covered in the feature's own test file"

No. Feature test files cover the happy path of that feature. The
isolation suite covers the cross-cutting invariant. Both are needed.
If we rely on per-feature tests to cover isolation, we will eventually
ship a feature where the author forgot — exactly what happened in
[postmortems/2026-04-17-get-tenant-cross-tenant-leak.md](./postmortems/2026-04-17-get-tenant-cross-tenant-leak.md).

## Current coverage

As of 2026-04-17, `test_cross_tenant_isolation.py` covers:

| Feature | Read | Write / state change |
|---|---|---|
| Members | ✓ | ✓ (PATCH) |
| Classes | ✓ | ✓ (PATCH, deactivate) |
| Plans | ✓ | ✓ (PATCH, deactivate) |
| Subscriptions | ✓ + events | ✓ (freeze, unfreeze, renew, change-plan, cancel) |
| Attendance | ✓ + summary + member-list | ✓ (record, undo) |
| Tenants | ✓ | ✓ (suspend) |
| Users | ✓ (list scoped) | — (super_admin only) |

Future features (Payments, Leads, Attendance v2 schedule) add their
endpoints here in the same PR.

## Related docs

- [`postmortems/2026-04-17-get-tenant-cross-tenant-leak.md`](./postmortems/2026-04-17-get-tenant-cross-tenant-leak.md) — the first real leak we caught with this suite.
- [`../standards/architecture.md`](../standards/architecture.md) — how the 4 layers fit together.
- [`../spec.md`](../spec.md) §Auth — JWT shape + role enum.
