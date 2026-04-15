import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import TenantUsersSection from "./TenantUsersSection"
import type { User } from "@/features/users/types"

vi.mock("@/features/users/hooks", () => ({
  useTenantUsers: vi.fn(),
  useCreateUser: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
}))

import { useTenantUsers } from "@/features/users/hooks"
const mockUsers = vi.mocked(useTenantUsers)

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TenantUsersSection tenantId="t1" />
    </QueryClientProvider>,
  )
}

const fakeUser: User = {
  id: "u1",
  email: "dana@gym.com",
  role: "owner",
  tenant_id: "t1",
  is_active: true,
  first_name: "Dana",
  last_name: "Cohen",
  phone: null,
  oauth_provider: null,
  created_at: "2026-04-14T12:00:00Z",
  updated_at: "2026-04-14T12:00:00Z",
}

describe("TenantUsersSection", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows empty-state when tenant has no users", () => {
    mockUsers.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    renderSection()
    expect(screen.getByText(/אין משתמשים עדיין/)).toBeInTheDocument()
  })

  it("renders user rows with name, email, and role badge", () => {
    mockUsers.mockReturnValue({ data: [fakeUser], isLoading: false, error: null } as any)
    renderSection()
    expect(screen.getByText("Dana Cohen")).toBeInTheDocument()
    expect(screen.getByText("dana@gym.com")).toBeInTheDocument()
    expect(screen.getByText("בעלים")).toBeInTheDocument() // Hebrew role label
  })

  it("falls back to email prefix when user has no name", () => {
    const noName = { ...fakeUser, first_name: null, last_name: null }
    mockUsers.mockReturnValue({ data: [noName], isLoading: false, error: null } as any)
    renderSection()
    expect(screen.getByText("dana")).toBeInTheDocument()
  })

  it("marks inactive users", () => {
    const inactive = { ...fakeUser, is_active: false }
    mockUsers.mockReturnValue({ data: [inactive], isLoading: false, error: null } as any)
    renderSection()
    expect(screen.getByText("לא פעיל")).toBeInTheDocument()
  })

  it("opens the inline create form when the + button is clicked", async () => {
    mockUsers.mockReturnValue({ data: [fakeUser], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderSection()
    await user.click(screen.getByText("+ הוסף משתמש"))
    // Form panel appears with its own headline + submit button
    expect(screen.getByText("משתמש חדש")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "הוסף משתמש" })).toBeInTheDocument()
  })
})
