import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import TenantStatsSection from "./TenantStatsSection"

vi.mock("./hooks", () => ({
  useTenantStats: vi.fn(),
}))

import { useTenantStats } from "./hooks"
const mockStats = vi.mocked(useTenantStats)

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TenantStatsSection tenantId="t1" />
    </QueryClientProvider>,
  )
}

describe("TenantStatsSection", () => {
  it("renders counts when data loads", () => {
    mockStats.mockReturnValue({
      data: { active_members: 38, total_members: 42, total_users: 5 },
      isLoading: false,
      error: null,
    } as any)
    renderSection()
    expect(screen.getByText("38")).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("5")).toBeInTheDocument()
    expect(screen.getByText(/מתוך 42 סה״כ/)).toBeInTheDocument()
  })

  it("shows loading placeholder while fetching", () => {
    mockStats.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderSection()
    expect(screen.getAllByText("…")).toHaveLength(3)
  })

  it("shows em-dash on error", () => {
    mockStats.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("boom"),
    } as any)
    renderSection()
    expect(screen.getAllByText("—")).toHaveLength(3)
  })

  it("defaults to 0 when counts are missing", () => {
    mockStats.mockReturnValue({
      data: { active_members: 0, total_members: 0, total_users: 0 },
      isLoading: false,
      error: null,
    } as any)
    renderSection()
    expect(screen.getAllByText("0")).toHaveLength(3)
  })
})
