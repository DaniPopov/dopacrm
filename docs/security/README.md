# Security docs

This folder holds:

1. **[cross-tenant-isolation.md](./cross-tenant-isolation.md)** — the
   core tenancy invariant every DopaCRM endpoint must honor: staff in
   gym A cannot read or mutate gym B's data under any circumstance.
   Includes the test pattern we use to enforce it.

2. **[postmortems/](./postmortems/)** — short write-ups of security
   bugs we caught (or almost caught). Each one documents the bug,
   the root cause, how we found it, and the process change that
   prevents the class from recurring.

## Why this folder exists

Security bugs in a multi-tenant SaaS are the worst class of bug:
- A one-line oversight can leak every gym's data to every other gym.
- The symptom is silent — no exception, no error log. You only find
  out when a customer does.
- They compound over time — every new feature is another chance to
  get it wrong.

Discipline beats heroics. We:

1. Write a consolidated cross-tenant isolation test suite
   (`backend/tests/e2e/test_cross_tenant_isolation.py`) that probes
   **every** gym-scoped endpoint from a foreign tenant's token.
2. Every new feature adds its endpoints to that suite as part of
   the PR — not after.
3. When a bug slips through, we write a post-mortem here so the
   pattern shows up in the next review.

## When to add a doc here

- Any bug where tenant A could access tenant B's data (even if caught
  in dev before production).
- Any authZ/authN bug (JWT handling, role escalation, etc.).
- Any data-exposure bug at the API layer (leaky error messages,
  missing scoping, etc.).

Everyday bugs (validation, UI copy, perf) don't belong here.
