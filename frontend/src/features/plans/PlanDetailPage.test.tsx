import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import PlanDetailPage from "./PlanDetailPage"
import type { MembershipPlan } from "./types"

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  )
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: "p1" }),
  }
})

vi.mock("./hooks", () => ({
  usePlan: vi.fn(),
  useUpdatePlan: vi.fn(),
}))

vi.mock("@/features/classes/hooks", () => ({
  useClasses: vi.fn(() => ({
    data: [{ id: "cl1", name: "יוגה", is_active: true }],
    isLoading: false,
    error: null,
  })),
}))

import { usePlan, useUpdatePlan } from "./hooks"
const mockUsePlan = vi.mocked(usePlan)
const mockUseUpdatePlan = vi.mocked(useUpdatePlan)

const fakePlan: MembershipPlan = {
  id: "p1",
  tenant_id: "t1",
  name: "חודשי",
  description: "מסלול חודשי",
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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PlanDetailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("PlanDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseUpdatePlan.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
  })

  it("shows loading while fetching", () => {
    mockUsePlan.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows an error when the fetch fails", () => {
    mockUsePlan.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("boom"),
    } as any)
    renderPage()
    expect(screen.getByText("boom")).toBeInTheDocument()
  })

  it("falls back to Hebrew 'not found' when error has no message", () => {
    mockUsePlan.mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("המסלול לא נמצא")).toBeInTheDocument()
  })

  it("renders header + form when the plan loads", () => {
    mockUsePlan.mockReturnValue({
      data: fakePlan,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("עריכת חודשי")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "שמור שינויים" })).toBeInTheDocument()
  })

  it("submit calls mutate with {id, data} and navigates on success", async () => {
    const mutate = vi.fn((_args, opts) => opts?.onSuccess?.())
    mockUseUpdatePlan.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUsePlan.mockReturnValue({
      data: fakePlan,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(mutate).toHaveBeenCalledTimes(1)
    const [args] = mutate.mock.calls[0]
    expect(args.id).toBe("p1")
    expect(args.data.name).toBe("חודשי")
    expect(mockNavigate).toHaveBeenCalledWith("/plans")
  })

  it("cancel navigates back without mutating", async () => {
    const mutate = vi.fn()
    mockUseUpdatePlan.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUsePlan.mockReturnValue({
      data: fakePlan,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "ביטול" }))

    expect(mutate).not.toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith("/plans")
  })

  it("back-link navigates to /plans", async () => {
    mockUsePlan.mockReturnValue({
      data: fakePlan,
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("← חזרה לרשימה"))
    expect(mockNavigate).toHaveBeenCalledWith("/plans")
  })

  it("mutation error surfaces through humanizePlanError (409 → phrase in Hebrew)", () => {
    mockUseUpdatePlan.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: Object.assign(new Error("dup"), { status: 409 }),
    } as any)
    mockUsePlan.mockReturnValue({
      data: fakePlan,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("מסלול בשם זה כבר קיים בחדר הכושר")).toBeInTheDocument()
  })
})
