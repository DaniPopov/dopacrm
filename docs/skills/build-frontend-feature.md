# Skill: Build a new frontend feature

> Step-by-step recipe for adding a new feature (e.g. Members, Leads, Classes) to the React frontend. Follow this in order — each step builds on the previous one.

## Before you start

Make sure the backend has:
- Migration applied, entities exist, repository + service + API routes are in place
- Feature doc in `docs/features/<feature>.md`
- You can hit the API from Swagger (`http://localhost:8000/docs`)

If not, build the backend first (see [`build-backend-feature.md`](./build-backend-feature.md)).

---

## Step 1 — Create the feature folder

```
frontend/src/features/<feature>/
├── types.ts          # TS types (mirror backend schemas)
├── api.ts            # Pure fetch functions
├── hooks.ts          # TanStack Query wrappers
├── <Feature>Form.tsx     # Shared create/edit form (if there's a form)
├── <Feature>ListPage.tsx # Main page
└── <Feature>ListPage.test.tsx
```

Always co-locate tests next to code. `api.test.ts` for API tests, `*.test.tsx` for component tests.

---

## Step 2 — `types.ts` — mirror the backend

Copy the shape from the backend's `TenantResponse` / `CreateXRequest` Pydantic models.

```typescript
export type MemberStatus = "active" | "frozen" | "cancelled"

export interface Member {
  id: string
  tenant_id: string
  first_name: string
  last_name: string
  status: MemberStatus
  // ... all fields from backend response
  created_at: string
  updated_at: string
}

export interface CreateMemberRequest {
  first_name: string
  last_name: string
  // ... required fields (no id, created_at, etc.)
}

export interface UpdateMemberRequest {
  first_name?: string
  last_name?: string
  // ... partial update
}
```

**Rules:**
- `string` for UUIDs and timestamps (JSON serialization)
- Use TypeScript union types (`"a" | "b"`) for enums
- Every nullable backend field should be `T | null`, not `T | undefined`

---

## Step 3 — `api.ts` — pure fetch functions

Use `apiClient` for everything. No React, no hooks, no error humanization — just typed HTTP calls.

```typescript
import { apiClient } from "@/lib/api-client"
import type { CreateMemberRequest, Member, UpdateMemberRequest } from "./types"

export function listMembers(): Promise<Member[]> {
  return apiClient.get("/members")
}

export function getMember(id: string): Promise<Member> {
  return apiClient.get(`/members/${id}`)
}

export function createMember(data: CreateMemberRequest): Promise<Member> {
  return apiClient.post("/members", data)
}

export function updateMember(id: string, data: UpdateMemberRequest): Promise<Member> {
  return apiClient.patch(`/members/${id}`, data)
}

/** Soft-delete / status change. Use dedicated endpoints, not PATCH. */
export function freezeMember(id: string): Promise<Member> {
  return apiClient.post(`/members/${id}/freeze`)
}
```

**Rules:**
- Every failure throws `ApiError` automatically (from `api-client.ts`)
- Status-change actions use dedicated POST endpoints, not PATCH with `status`
- File uploads use raw `fetch` + FormData + `credentials: "include"` (not `apiClient`)

---

## Step 4 — `hooks.ts` — wrap api.ts with TanStack Query

One hook per API function. Mutations invalidate the list query on success.

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createMember,
  freezeMember,
  getMember,
  listMembers,
  updateMember,
} from "./api"
import type { CreateMemberRequest, UpdateMemberRequest } from "./types"

export function useMembers() {
  return useQuery({
    queryKey: ["members"],
    queryFn: listMembers,
  })
}

export function useMember(id: string) {
  return useQuery({
    queryKey: ["members", id],
    queryFn: () => getMember(id),
    enabled: !!id,
  })
}

export function useCreateMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateMemberRequest) => createMember(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
  })
}

export function useUpdateMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateMemberRequest }) =>
      updateMember(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
  })
}

export function useFreezeMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => freezeMember(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
  })
}
```

**Rules:**
- `queryKey` uses the feature name as the first segment (`["members"]`)
- Detail queries add the id as a second segment (`["members", id]`)
- All mutations `invalidateQueries` to refresh any open list/detail views

---

## Step 5 — Add a humanizer to `lib/api-errors.ts`

If your feature has domain-specific error messages (slug collision, limit exceeded, etc.), add a `humanizeMemberError` function:

```typescript
export function humanizeMemberError(err: unknown): string {
  if (err instanceof ApiError || (err instanceof Error && "status" in err)) {
    const status = (err as ApiError).status
    if (status === 409) return "אימייל כבר בשימוש"
    if (status === 422) return "הפרטים שהוזנו אינם תקינים"
    if (status === 402) return "הגעת למגבלת המנויים של התוכנית"
    return genericMessage(status)
  }
  return "אירעה שגיאה בשמירת המנוי"
}
```

**Rules:**
- Always fall through to `genericMessage(status)` for unhandled codes
- Domain-specific codes (402, 409, etc.) get their own message
- Write messages in the user's target language (Hebrew for DopaCRM)

---

## Step 6 — Build the form (if needed)

Extract the form to its own file if it'll be reused by Create + Edit dialogs. Use plain `useState` for ~15 fields, `react-hook-form` only if it grows bigger.

```tsx
// features/members/MemberForm.tsx
interface MemberFormProps {
  initial?: Partial<Member>
  submitting?: boolean
  error?: string | null
  submitLabel: string
  onSubmit: (values: CreateMemberRequest) => void
  onCancel: () => void
}

export default function MemberForm({ initial, submitting, error, submitLabel, onSubmit, onCancel }: MemberFormProps) {
  const [form, setForm] = useState({ first_name: initial?.first_name ?? "", /* ... */ })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Section title="פרטים אישיים">
        <Field label="שם פרטי *">
          <input required value={form.first_name} onChange={...} className={inputClass} />
        </Field>
        {/* more fields */}
      </Section>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">{error}</div>}

      <div className="flex justify-end gap-3 border-t border-gray-100 pt-4">
        <button type="button" onClick={onCancel}>ביטול</button>
        <button type="submit" disabled={submitting}>{submitting ? "שומר..." : submitLabel}</button>
      </div>
    </form>
  )
}
```

**Pattern:** group fields into `<Section>` cards with `<Field>` wrappers (see `TenantForm.tsx` for the shared `Section`/`Field`/`inputClass` helpers — copy them if needed).

---

## Step 7 — Build the list page

```tsx
// features/members/MemberListPage.tsx
import { useState } from "react"
import { humanizeMemberError } from "@/lib/api-errors"
import MemberForm from "./MemberForm"
import { useCreateMember, useMembers, useUpdateMember, useFreezeMember } from "./hooks"
import type { Member } from "./types"

export default function MemberListPage() {
  const { data, isLoading, error } = useMembers()
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)
  const create = useCreateMember()
  const update = useUpdateMember()

  return (
    <div>
      <Header onAdd={() => setShowCreate(true)} />

      {showCreate && (
        <CreateCard
          onSubmit={(values) => create.mutate(values, { onSuccess: () => setShowCreate(false) })}
          submitting={create.isPending}
          error={create.error ? humanizeMemberError(create.error) : null}
          onClose={() => setShowCreate(false)}
        />
      )}

      {editing && (
        <EditDialog
          member={editing}
          submitting={update.isPending}
          error={update.error ? humanizeMemberError(update.error) : undefined}
          onSubmit={(values) => update.mutate({ id: editing.id, data: values }, { onSuccess: () => setEditing(null) })}
          onClose={() => setEditing(null)}
        />
      )}

      {isLoading ? <Loading /> : <MemberTable members={data ?? []} onEdit={setEditing} />}
    </div>
  )
}
```

**Rules:**
- Loading / error / empty / data states — always all four
- Use `humanizeXError()` to display mutation errors
- Pass row-level callbacks (`onEdit`) down — don't have the row reach up into the page's state

---

## Step 8 — Add row actions

Use a dropdown menu with conditional items based on the row's status:

```tsx
function MemberRow({ member, onEdit }: { member: Member; onEdit: () => void }) {
  const freeze = useFreezeMember()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <>
      <tr>
        <td>{member.first_name} {member.last_name}</td>
        <td><StatusBadge status={member.status} /></td>
        <td>
          <button onClick={() => setMenuOpen(v => !v)}>פעולות ▾</button>
          {menuOpen && (
            <div className="absolute ..." onMouseLeave={() => setMenuOpen(false)}>
              <MenuItem label="עריכה" onClick={onEdit} />
              {member.status === "active" && (
                <MenuItem label="הקפא" onClick={() => freeze.mutate(member.id)} />
              )}
              <MenuItem label="ביטול" variant="danger" onClick={() => setConfirmCancel(true)} />
            </div>
          )}
        </td>
      </tr>
      {confirmCancel && (
        <ConfirmDialog
          title="ביטול מנוי"
          message={`האם לבטל את ${member.first_name}?`}
          variant="danger"
          onConfirm={() => { /* mutate */ }}
          onCancel={() => setConfirmCancel(false)}
        />
      )}
    </>
  )
}
```

Copy `ConfirmDialog` and `MenuItem` from `TenantListPage.tsx` — or extract them to `components/layout/` if reused 3+ times.

---

## Step 9 — Wire into the router

```tsx
// app/App.tsx
import MemberListPage from "@/features/members/MemberListPage"

<Route element={<ProtectedRoute />}>
  <Route element={<DashboardLayout />}>
    <Route path="/members" element={<MemberListPage />} />
  </Route>
</Route>
```

And add a sidebar link in `components/layout/DashboardLayout.tsx`:

```tsx
<SidebarLink to="/members" icon="👥" label="מנויים" />
```

Wrap in a role check if it's role-gated.

---

## Step 10 — Tests

### `api.test.ts` (5-10 tests)

Mock `apiClient` and verify each function calls the right endpoint with the right body.

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest"

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: mockGet, post: mockPost, /* ... */ },
}))

import { listMembers, createMember } from "./api"

beforeEach(() => vi.clearAllMocks())

describe("members api", () => {
  it("listMembers calls GET /members", async () => {
    mockGet.mockResolvedValue([])
    await listMembers()
    expect(mockGet).toHaveBeenCalledWith("/members")
  })

  it("createMember calls POST /members with body", async () => {
    mockPost.mockResolvedValue({ id: "new" })
    await createMember({ first_name: "Dani", last_name: "Popov" })
    expect(mockPost).toHaveBeenCalledWith("/members", { first_name: "Dani", last_name: "Popov" })
  })
})
```

### `<Page>.test.tsx` (10-15 tests)

Mock all hooks, render with `MemoryRouter` + `QueryClientProvider`, assert:
- loading state
- empty state
- renders table with data
- status badges
- opens create form when header button clicked
- actions menu shows correct items per status
- confirmation dialog appears on destructive actions
- edit dialog opens with prefilled data

Use role-based queries (`getByRole("button", { name: ... })`) to avoid ambiguous text matches (e.g. "פעולות" might appear in both header and row).

---

## Step 11 — Run everything

```bash
# Type check
cd frontend && npx tsc --noEmit

# Tests
npx vitest run

# Or via Make (includes backend)
make test-all-dev
```

All green? Commit.

---

## Checklist

- [ ] Feature folder created with `types.ts`, `api.ts`, `hooks.ts`
- [ ] Types mirror backend response/request schemas
- [ ] `api.ts` uses `apiClient` (no React)
- [ ] `hooks.ts` wraps every API function with TanStack Query
- [ ] Humanizer added to `lib/api-errors.ts` if domain-specific errors exist
- [ ] Form extracted to its own file if Create + Edit share it
- [ ] List page has loading / error / empty / data states
- [ ] Row actions use dropdown + confirmation dialogs for destructive ops
- [ ] Errors shown to users go through `humanize*Error` (never raw backend detail)
- [ ] Route added to `app/App.tsx`
- [ ] Sidebar link added to `DashboardLayout.tsx` (role-gated if needed)
- [ ] `api.test.ts` covers every function
- [ ] `<Page>.test.tsx` covers loading / empty / render / actions / dialogs
- [ ] `npx tsc --noEmit` passes
- [ ] `npx vitest run` passes
- [ ] Feature doc added at `docs/features/<feature>.md`
