import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import PlanListPage from "./PlanListPage"
import type { MembershipPlan } from "./types"

/**
 * PlanListPage — catalog list + inline create + row actions.
 *
 * Covers the same shape as ClassListPage + the plan-specific bits:
 * - formatted price displays correctly
 * - "ללא הגבלה" renders when entitlements is empty
 * - non-empty entitlements render as quota summary lines
 */

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  )
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock("./hooks", () => ({
  usePlans: vi.fn(),
  useCreatePlan: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useDeactivatePlan: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useActivatePlan: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

vi.mock("@/features/classes/hooks", () => ({
  useClasses: vi.fn(() => ({
    data: [
      { id: "cl1", name: "ספינינג", is_active: true },
      { id: "cl2", name: "יוגה", is_active: true },
    ],
    isLoading: false,
    error: null,
  })),
}))

const mockUseAuth = vi.fn()
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}))

import { usePlans } from "./hooks"
const mockUsePlans = vi.mocked(usePlans)

const unlimitedPlan: MembershipPlan = {
  id: "p1",
  tenant_id: "t1",
  name: "מלא",
  description: "גישה לכל השיעורים",
  type: "recurring",
  price_cents: 45000,
  currency: "ILS",
  billing_period: "monthly",
  duration_days: null,
  is_active: true,
  custom_attrs: {},
  entitlements: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const meteredPlan: MembershipPlan = {
  ...unlimitedPlan,
  id: "p2",
  name: "3 קבוצתיים",
  entitlements: [
    {
      id: "e1",
      plan_id: "p2",
      class_id: "cl2",
      quantity: 3,
      reset_period: "weekly",
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
}

function renderPage(userOverrides: Record<string, unknown> = {}) {
  mockUseAuth.mockReturnValue({ user: { role: "owner", ...userOverrides } })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PlanListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("PlanListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows loading state", () => {
    mockUsePlans.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows empty state when no plans", () => {
    mockUsePlans.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText(/אין מסלולים/)).toBeInTheDocument()
  })

  it("renders plan name + price + billing + active badge", () => {
    mockUsePlans.mockReturnValue({
      data: [unlimitedPlan],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("מלא")).toBeInTheDocument()
    // Price formatted with ₪ and shekel amount (450)
    expect(screen.getByText(/₪450/)).toBeInTheDocument()
    expect(screen.getByText("חודשי")).toBeInTheDocument()
    expect(screen.getByText("פעיל")).toBeInTheDocument()
  })

  it("shows 'ללא הגבלה' when entitlements is empty", () => {
    mockUsePlans.mockReturnValue({
      data: [unlimitedPlan],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("ללא הגבלה")).toBeInTheDocument()
  })

  it("renders entitlement quota summary with class name + cadence", () => {
    mockUsePlans.mockReturnValue({
      data: [meteredPlan],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    // "3 × יוגה (שבועי)"
    expect(screen.getByText(/3 × יוגה/)).toBeInTheDocument()
  })

  it("clicking plan name navigates to /plans/:id", async () => {
    mockUsePlans.mockReturnValue({
      data: [unlimitedPlan],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("מלא"))
    expect(mockNavigate).toHaveBeenCalledWith("/plans/p1")
  })

  it("owner sees the add button", () => {
    mockUsePlans.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "owner" })
    expect(screen.getByText("+ מסלול חדש")).toBeInTheDocument()
  })

  it("staff does not see the add button", () => {
    mockUsePlans.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "staff" })
    expect(screen.queryByText("+ מסלול חדש")).not.toBeInTheDocument()
  })

  it("staff sees 'view only' placeholder instead of the actions menu", () => {
    mockUsePlans.mockReturnValue({
      data: [unlimitedPlan],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "staff" })
    expect(screen.getByText("צפייה בלבד")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /פעולות/ })).not.toBeInTheDocument()
  })

  it("active plan: actions menu shows 'השבתה' (not 'הפעלה')", async () => {
    mockUsePlans.mockReturnValue({
      data: [unlimitedPlan],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage({ role: "owner" })
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("השבתה")).toBeInTheDocument()
    expect(screen.queryByText("הפעלה")).not.toBeInTheDocument()
  })

  it("inactive plan: actions menu shows 'הפעלה' (not 'השבתה')", async () => {
    mockUsePlans.mockReturnValue({
      data: [{ ...unlimitedPlan, is_active: false }],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage({ role: "owner" })
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("הפעלה")).toBeInTheDocument()
    expect(screen.queryByText("השבתה")).not.toBeInTheDocument()
  })

  it("opens inline create form when + button is clicked (owner)", async () => {
    mockUsePlans.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage({ role: "owner" })
    await user.click(screen.getByText("+ מסלול חדש"))
    expect(screen.getByText("מסלול חדש", { selector: "h3" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "צור מסלול" })).toBeInTheDocument()
  })
})
