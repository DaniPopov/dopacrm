import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import MemberListPage from "./MemberListPage"
import type { Member } from "./types"

// Navigation stub — lets us verify "click name → navigate to /members/:id"
const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock("./hooks", () => ({
  useMembers: vi.fn(),
  useCreateMember: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useFreezeMember: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUnfreezeMember: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCancelMember: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role: "owner" } }),
}))

import { useMembers } from "./hooks"
const mockUseMembers = vi.mocked(useMembers)

const fakeMember: Member = {
  id: "m1",
  tenant_id: "t1",
  first_name: "Dana",
  last_name: "Cohen",
  phone: "+972-50-123-4567",
  email: "dana@example.com",
  date_of_birth: null,
  gender: "female",
  status: "active",
  join_date: "2026-04-14",
  frozen_at: null,
  frozen_until: null,
  cancelled_at: null,
  notes: null,
  custom_fields: {},
  created_at: "2026-04-14T12:00:00Z",
  updated_at: "2026-04-14T12:00:00Z",
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MemberListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("MemberListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows loading state", () => {
    mockUseMembers.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows empty state when no members", () => {
    mockUseMembers.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText(/אין מנויים עדיין/)).toBeInTheDocument()
  })

  it("renders member in the table with name, phone, status", () => {
    mockUseMembers.mockReturnValue({
      data: [fakeMember],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("Dana Cohen")).toBeInTheDocument()
    expect(screen.getByText("+972-50-123-4567")).toBeInTheDocument()
    // "פעיל" appears in the filter chip AND the row badge — both are fine
    expect(screen.getAllByText("פעיל").length).toBeGreaterThanOrEqual(2)
  })

  it("status badge shows the right label for frozen", () => {
    mockUseMembers.mockReturnValue({
      data: [{ ...fakeMember, status: "frozen" }],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    // Filter chip + row badge = 2 "מוקפא" elements
    expect(screen.getAllByText("מוקפא").length).toBeGreaterThanOrEqual(2)
  })

  it("opens create form when + button is clicked", async () => {
    mockUseMembers.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("+ הוספת מנוי"))
    expect(screen.getByText("מנוי חדש")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "צור מנוי" })).toBeInTheDocument()
  })

  it("clicking member name navigates to /members/:id", async () => {
    mockUseMembers.mockReturnValue({
      data: [fakeMember],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("Dana Cohen"))
    expect(mockNavigate).toHaveBeenCalledWith("/members/m1")
  })

  it("actions menu shows Freeze for active members", async () => {
    mockUseMembers.mockReturnValue({
      data: [fakeMember],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("הקפאה")).toBeInTheDocument()
    expect(screen.queryByText("ביטול הקפאה")).not.toBeInTheDocument()
  })

  it("actions menu shows Unfreeze for frozen members", async () => {
    mockUseMembers.mockReturnValue({
      data: [{ ...fakeMember, status: "frozen" }],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("ביטול הקפאה")).toBeInTheDocument()
    expect(screen.queryByText("הקפאה")).not.toBeInTheDocument()
  })

  it("cancelled members show no status-change actions", async () => {
    mockUseMembers.mockReturnValue({
      data: [{ ...fakeMember, status: "cancelled" }],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("עריכה")).toBeInTheDocument()
    expect(screen.queryByText("הקפאה")).not.toBeInTheDocument()
    expect(screen.queryByText("ביטול הקפאה")).not.toBeInTheDocument()
    expect(screen.queryByText("ביטול חברות")).not.toBeInTheDocument()
  })
})
