# Feature Documentation Standard

> Every feature gets a markdown file in ``docs/features/``. When a dev
> finishes a feature, the doc is the deliverable alongside the code.
> A PM or another dev should be able to read the doc and understand
> everything that was built without reading the source.

## File naming

```
docs/features/{feature-name}.md
```

Examples: ``users.md``, ``conversations.md``, ``whatsapp-webhook.md``,
``priority-erp.md``, ``config-service.md``.

Lowercase, hyphen-separated, matches the bounded context name.

## Template

Every feature doc follows this structure. Copy-paste this template when
starting a new feature:

````markdown
# Feature: {Name}

## Summary

One paragraph: what this feature does, who uses it, and why it exists.

## API Endpoints

| Method | Route | Auth | Rate limit | Description |
|--------|-------|------|------------|-------------|
| POST | /api/v1/... | super_admin | 10/min/IP | Create ... |
| GET | /api/v1/... | Bearer | 60/min/user | List ... |

## Domain (Layer 3)

### Entities

List every Pydantic entity this feature uses or created.

- ``domain/entities/{name}.py`` — fields, enums, purpose

### Pure logic methods

List the business-rule methods on the entity (if any):

- ``should_send_reminder(now)`` — returns True if inactive for 90+ min
- ``close(reason)`` — transitions status to CLOSED

### Exceptions

List the domain exceptions this feature raises:

- ``UserNotFoundError`` → 404
- ``UserAlreadyExistsError`` → 409

## Service (Layer 2)

File: ``services/{name}_service.py``

List every method with a one-line description:

- ``create_user(caller, email, role, ...)`` — permission check + hash + repo
- ``list_users(caller, limit, offset)`` — company-scoped by caller role
- ``soft_delete_user(user_id)`` — sets is_active=False

### Business rules (what the service enforces)

- Only super_admin can create users
- Non-super_admin roles require a company_id
- List returns only the caller's company (unless super_admin)

## Adapter (Layer 4)

### Database model

File: ``adapters/storage/postgres/{entity}/models.py``

Table name, key columns, constraints, indexes.

### Repository methods

File: ``adapters/storage/postgres/{entity}/repositories.py``

- ``create(...)`` — INSERT, catches IntegrityError → domain exception
- ``find_by_id(id)`` — SELECT by PK
- ``list_all(limit, offset)`` — paginated, ordered by created_at DESC
- ``update(id, **fields)`` — partial UPDATE

### Migrations

- ``0001_create_users_companies_tokens.py`` — creates 3 tables

## API (Layer 1)

### Routes

File: ``api/v1/{feature}/router.py``

Describe each route handler briefly — what it parses, what service method
it calls, what it returns.

### Schemas

File: ``api/v1/{feature}/schemas.py``

List request/response models with example JSON.

### Dependencies used

- ``get_current_user`` — JWT validation
- ``require_super_admin`` — permission gate
- ``api_rate_limit`` — 60/min per user

## Tests

| Type | File | What it covers |
|------|------|----------------|
| Unit | ``tests/unit/test_{name}.py`` | Entity pure logic, security utils |
| Integration | ``tests/integration/test_{name}_repo.py`` | Repo against real Postgres |
| E2E | ``tests/e2e/test_{name}.py`` | Full HTTP route tests |

### Test count

- Unit: X tests
- Integration: X tests
- E2E: X tests

## Decisions

Document any non-obvious choices made during implementation:

- **Soft-delete vs hard-delete** — chose soft-delete (is_active=False)
  because user data is referenced by conversations and audit trails.
- **Role as CHECK constraint vs Postgres ENUM** — chose CHECK because
  ENUMs are hard to migrate (can't easily add values).

## Database schema

```sql
CREATE TABLE ... (
    ...
);
```

## Swagger

How to test this feature from http://localhost:8000/docs:

1. Login → copy token → Authorize
2. Try endpoint X with example payload
3. Verify response
````

## Rules

1. **Write the doc as you build** — not after. If you wait, you forget
   details and skip it.
2. **One feature = one doc** — don't combine "users + auth" into one file.
   If they have separate routes, they get separate docs.
3. **Include actual JSON** — don't just say "sends a request". Show the
   body. Show the response. A dev should be able to curl it.
4. **List every file** — the doc should name every file the feature
   touches. A reviewer can diff the doc against the PR and check nothing
   is missing.
5. **Decisions section is mandatory** — if you made a choice, write why.
   Future-you won't remember. The PM won't know unless you write it.
6. **Update when the feature changes** — if you add an endpoint or change
   a business rule, update the doc in the same PR.
