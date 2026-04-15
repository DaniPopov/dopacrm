import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import AdminDashboard from "./AdminDashboard"

vi.mock("./hooks", () => ({
  usePlatformStats: vi.fn(),
}))

import { usePlatformStats } from "./hooks"
const mockStats = vi.mocked(usePlatformStats)

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AdminDashboard />
    </QueryClientProvider>,
  )
}

describe("AdminDashboard", () => {
  it("renders all four platform stats when data loads", () => {
    mockStats.mockReturnValue({
      data: {
        total_tenants: 12,
        active_tenants: 10,
        new_tenants_this_month: 3,
        total_users: 45,
        total_members: 387,
      },
      isLoading: false,
      error: null,
    } as any)
    renderDashboard()
    expect(screen.getByText("12")).toBeInTheDocument()
    expect(screen.getByText("10")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("45")).toBeInTheDocument()
    // total_members surfaces as a hint on the users card
    expect(screen.getByText("387 מנויים במערכת")).toBeInTheDocument()
  })

  it("shows loading placeholder while fetching", () => {
    mockStats.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderDashboard()
    expect(screen.getAllByText("…")).toHaveLength(4)
  })

  it("shows em-dash on error", () => {
    mockStats.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("nope"),
    } as any)
    renderDashboard()
    expect(screen.getAllByText("—")).toHaveLength(4)
  })

  it("includes the Hebrew header and subtitle", () => {
    mockStats.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderDashboard()
    expect(screen.getByText("דשבורד ניהול פלטפורמה")).toBeInTheDocument()
    expect(screen.getByText(/מבט על על כל חדרי הכושר במערכת/)).toBeInTheDocument()
  })
})
