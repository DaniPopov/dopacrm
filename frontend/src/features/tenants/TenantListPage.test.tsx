import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import TenantListPage from "./TenantListPage"
import type { Tenant } from "./types"

// Capture navigate() calls so we can assert Edit routes to /tenants/:id
const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

// Mock all the hooks used by the page + its children
vi.mock("./hooks", () => ({
  useTenants: vi.fn(),
  useCreateTenant: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useUpdateTenant: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useSuspendTenant: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useActivateTenant: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCancelTenant: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUploadLogo: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  })),
}))

import { useTenants } from "./hooks"
const mockUseTenants = vi.mocked(useTenants)

const fakeTenant: Tenant = {
  id: "t1",
  slug: "ironfit-tlv",
  name: "IronFit Tel Aviv",
  status: "active",
  saas_plan_id: "plan-1",
  logo_url: null,
  logo_presigned_url: null,
  phone: "+972-3-555-1234",
  email: null,
  website: null,
  address_street: null,
  address_city: "Tel Aviv",
  address_country: "IL",
  address_postal_code: null,
  legal_name: null,
  tax_id: null,
  timezone: "Asia/Jerusalem",
  currency: "ILS",
  locale: "he-IL",
  trial_ends_at: null,
  created_at: "2026-04-10T10:00:00Z",
  updated_at: "2026-04-10T10:00:00Z",
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TenantListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("TenantListPage", () => {
  it("shows loading state", () => {
    mockUseTenants.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows empty state", () => {
    mockUseTenants.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText(/אין חדרי כושר עדיין/)).toBeInTheDocument()
  })

  it("renders tenant table with data", () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("IronFit Tel Aviv")).toBeInTheDocument()
    expect(screen.getByText("ironfit-tlv")).toBeInTheDocument()
    expect(screen.getByText("פעיל")).toBeInTheDocument()
    expect(screen.getByText("ILS")).toBeInTheDocument()
    expect(screen.getByText("Tel Aviv")).toBeInTheDocument()
  })

  it("shows suspended badge for suspended tenant", () => {
    const suspended = { ...fakeTenant, id: "t2", status: "suspended" as const }
    mockUseTenants.mockReturnValue({
      data: [suspended],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("מושהה")).toBeInTheDocument()
  })

  it("shows trial badge for trial tenant", () => {
    const trial = { ...fakeTenant, id: "t3", status: "trial" as const }
    mockUseTenants.mockReturnValue({ data: [trial], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("ניסיון")).toBeInTheDocument()
  })

  it("opens create form when header button clicked", async () => {
    mockUseTenants.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("+ הוספת חדר כושר"))
    expect(screen.getByText("חדר כושר חדש")).toBeInTheDocument()
    expect(screen.getByText("פרטי חדר כושר")).toBeInTheDocument()
  })

  it("renders initial avatar when no logo", () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    renderPage()
    // First letter of name should be visible as fallback
    expect(screen.getByText("I")).toBeInTheDocument()
  })

  it("shows actions button per row", () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByRole("button", { name: /פעולות/ })).toBeInTheDocument()
  })

  it("opens actions menu with Edit/Suspend/Cancel for active tenant", async () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("עריכה")).toBeInTheDocument()
    expect(screen.getByText("השהה")).toBeInTheDocument()
    expect(screen.getByText("ביטול (מחיקה רכה)")).toBeInTheDocument()
    // Activate should NOT show for active tenants
    expect(screen.queryByText("הפעל")).not.toBeInTheDocument()
  })

  it("shows Activate action for suspended tenants", async () => {
    const suspended = { ...fakeTenant, id: "t2", status: "suspended" as const }
    mockUseTenants.mockReturnValue({
      data: [suspended],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("הפעל")).toBeInTheDocument()
    // Suspend should NOT show
    expect(screen.queryByText("השהה")).not.toBeInTheDocument()
  })

  it("opens confirmation dialog when Cancel is clicked", async () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    await user.click(screen.getByText("ביטול (מחיקה רכה)"))
    expect(screen.getByText("ביטול חדר כושר")).toBeInTheDocument()
    expect(screen.getByText("כן, בטל")).toBeInTheDocument()
  })

  it("navigates to /tenants/:id when Edit is clicked", async () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    mockNavigate.mockClear()
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    await user.click(screen.getByText("עריכה"))
    expect(mockNavigate).toHaveBeenCalledWith("/tenants/t1")
  })
})
