import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import TenantListPage from "./TenantListPage"
import type { Tenant } from "./types"

// Mock the hooks
vi.mock("./hooks", () => ({
  useTenants: vi.fn(),
  useCreateTenant: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
  useSuspendTenant: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

import { useTenants } from "./hooks"
const mockUseTenants = vi.mocked(useTenants)

const fakeTenant: Tenant = {
  id: "t1",
  slug: "ironfit-tlv",
  name: "IronFit Tel Aviv",
  phone: "+972-3-555-1234",
  status: "active",
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
  })

  it("shows suspended badge for suspended tenant", () => {
    const suspended = { ...fakeTenant, id: "t2", status: "suspended" as const }
    mockUseTenants.mockReturnValue({ data: [suspended], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("מושהה")).toBeInTheDocument()
  })

  it("shows create form when button clicked", async () => {
    mockUseTenants.mockReturnValue({ data: [], isLoading: false, error: null } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("+ הוספת חדר כושר"))
    expect(screen.getByText("חדר כושר חדש")).toBeInTheDocument()
  })

  it("hides suspend button for already suspended tenants", () => {
    const suspended = { ...fakeTenant, id: "t2", status: "suspended" as const }
    mockUseTenants.mockReturnValue({ data: [suspended], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.queryByText("השהה")).not.toBeInTheDocument()
  })

  it("shows suspend button for active tenants", () => {
    mockUseTenants.mockReturnValue({ data: [fakeTenant], isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("השהה")).toBeInTheDocument()
  })
})
