import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import Sidebar from "./Sidebar"

/**
 * Sidebar responsibilities tested here:
 * - Defaults to DopaCRM logo + name for super_admin (no tenant).
 * - Shows the tenant's logo + name when the user is tenant-scoped
 *   and useTenant has resolved.
 * - Falls back to DopaCRM defaults if the tenant has no logo.
 * - Collapse mode hides labels and the brand name, keeps icons.
 * - Collapse toggle button fires the parent handler.
 * - Renders the logout button.
 */

const mockLogout = vi.fn()
const mockUseAuth = vi.fn()
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}))

const mockUseTenant = vi.fn()
vi.mock("@/features/tenants/hooks", () => ({
  useTenant: (id: string) => mockUseTenant(id),
}))

function renderSidebar(props: Parameters<typeof Sidebar>[0] = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Sidebar {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const superAdmin = {
  id: "sa1",
  email: "admin@dopacrm.com",
  role: "super_admin" as const,
  tenant_id: null,
  is_active: true,
  first_name: null,
  last_name: null,
  phone: null,
  oauth_provider: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const tenantOwner = {
  ...superAdmin,
  id: "o1",
  email: "owner@dopamineo.test",
  role: "owner" as const,
  tenant_id: "t1",
}

const fakeTenant = {
  id: "t1",
  slug: "dopamineo",
  name: "דופמינו ג׳ים",
  status: "active",
  saas_plan_id: "plan1",
  logo_url: "logos/dopamineo.png",
  logo_presigned_url: "https://s3.example/dopamineo.png?sig=abc",
  phone: null,
  email: null,
  website: null,
  address_street: null,
  address_city: null,
  address_country: "IL",
  address_postal_code: null,
  legal_name: null,
  tax_id: null,
  timezone: "Asia/Jerusalem",
  currency: "ILS",
  locale: "he-IL",
  trial_ends_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

describe("Sidebar — branding", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({ user: superAdmin, logout: mockLogout })
    mockUseTenant.mockReturnValue({ data: undefined })
  })

  it("shows DopaCRM + dopa-icon for super_admin (no tenant)", () => {
    const { container } = renderSidebar()
    expect(screen.getByText("DopaCRM")).toBeInTheDocument()
    const logo = container.querySelector("img")
    expect(logo?.getAttribute("src")).toContain("dopa-icon")
  })

  it("shows the tenant name + logo when tenant-scoped user has a resolved tenant", () => {
    mockUseAuth.mockReturnValue({ user: tenantOwner, logout: mockLogout })
    mockUseTenant.mockReturnValue({ data: fakeTenant })
    const { container } = renderSidebar()
    expect(screen.getByText("דופמינו ג׳ים")).toBeInTheDocument()
    const logo = container.querySelector("img")
    expect(logo?.getAttribute("src")).toBe(
      "https://s3.example/dopamineo.png?sig=abc",
    )
  })

  it("falls back to DopaCRM defaults when the tenant has no logo", () => {
    mockUseAuth.mockReturnValue({ user: tenantOwner, logout: mockLogout })
    mockUseTenant.mockReturnValue({
      data: { ...fakeTenant, logo_presigned_url: null },
    })
    const { container } = renderSidebar()
    expect(screen.getByText("דופמינו ג׳ים")).toBeInTheDocument() // name still from tenant
    const logo = container.querySelector("img")
    expect(logo?.getAttribute("src")).toContain("dopa-icon") // logo fell back
  })

  it("falls back to DopaCRM while tenant is still loading", () => {
    mockUseAuth.mockReturnValue({ user: tenantOwner, logout: mockLogout })
    mockUseTenant.mockReturnValue({ data: undefined })
    renderSidebar()
    expect(screen.getByText("DopaCRM")).toBeInTheDocument()
  })
})

describe("Sidebar — collapse", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({ user: superAdmin, logout: mockLogout })
    mockUseTenant.mockReturnValue({ data: undefined })
  })

  it("expanded: shows nav labels and the brand name", () => {
    renderSidebar({ collapsed: false, onToggleCollapse: vi.fn() })
    expect(screen.getByText("DopaCRM")).toBeInTheDocument()
    expect(screen.getByText("דשבורד")).toBeInTheDocument()
    expect(screen.getByText("חדרי כושר")).toBeInTheDocument()
  })

  it("collapsed: hides nav labels and the brand name", () => {
    renderSidebar({ collapsed: true, onToggleCollapse: vi.fn() })
    expect(screen.queryByText("DopaCRM")).not.toBeInTheDocument()
    expect(screen.queryByText("דשבורד")).not.toBeInTheDocument()
    expect(screen.queryByText("חדרי כושר")).not.toBeInTheDocument()
    // Icons are still present (as emoji inside NavLink)
    expect(screen.getByText("📊")).toBeInTheDocument()
  })

  it("collapse toggle button fires onToggleCollapse", async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderSidebar({ collapsed: false, onToggleCollapse: onToggle })
    await user.click(screen.getByRole("button", { name: "סגור סרגל" }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it("hides the collapse toggle entirely when onToggleCollapse is not provided", () => {
    renderSidebar() // no onToggleCollapse
    expect(screen.queryByRole("button", { name: /סרגל/ })).not.toBeInTheDocument()
  })
})

describe("Sidebar — logout", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({ user: superAdmin, logout: mockLogout })
    mockUseTenant.mockReturnValue({ data: undefined })
  })

  it("renders a logout button that fires logout on click", async () => {
    const user = userEvent.setup()
    renderSidebar()
    await user.click(screen.getByRole("button", { name: "התנתקות" }))
    expect(mockLogout).toHaveBeenCalledTimes(1)
  })
})
