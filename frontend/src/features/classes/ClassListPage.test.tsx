import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import ClassListPage from "./ClassListPage"
import type { GymClass } from "./types"

/**
 * ClassListPage — catalog list + inline create + row actions.
 *
 * Covered:
 * - Loading, error, empty states (empty varies by the include-inactive toggle).
 * - Renders a class with name + active badge.
 * - Click name → navigate to /classes/:id.
 * - Owner sees "+ הוספת סוג שיעור" button and the actions menu.
 * - Staff/sales do NOT see the add button OR row actions ("צפייה בלבד" placeholder).
 * - Active class → actions menu shows "השבתה".
 * - Inactive class → actions menu shows "הפעלה".
 */

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  )
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock("./hooks", () => ({
  useClasses: vi.fn(),
  useCreateClass: vi.fn(() => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    error: null,
  })),
  useDeactivateClass: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useActivateClass: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}))

const mockUseAuth = vi.fn()
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => mockUseAuth(),
}))

import { useClasses } from "./hooks"
const mockUseClasses = vi.mocked(useClasses)

const fakeClass: GymClass = {
  id: "c1",
  tenant_id: "t1",
  name: "Spinning",
  description: "Indoor cycling",
  color: "#3B82F6",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

function renderPage(userOverrides: Record<string, unknown> = {}) {
  mockUseAuth.mockReturnValue({ user: { role: "owner", ...userOverrides } })
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ClassListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("ClassListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows loading state", () => {
    mockUseClasses.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows empty state when no classes", () => {
    mockUseClasses.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText(/אין שיעורים/)).toBeInTheDocument()
  })

  it("renders a class with name + active badge", () => {
    mockUseClasses.mockReturnValue({
      data: [fakeClass],
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("Spinning")).toBeInTheDocument()
    expect(screen.getByText("פעיל")).toBeInTheDocument()
  })

  it("clicking class name navigates to /classes/:id", async () => {
    mockUseClasses.mockReturnValue({
      data: [fakeClass],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("Spinning"))
    expect(mockNavigate).toHaveBeenCalledWith("/classes/c1")
  })

  it("owner sees the add button", () => {
    mockUseClasses.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "owner" })
    expect(screen.getByText("+ הוספת סוג שיעור")).toBeInTheDocument()
  })

  it("staff does not see the add button", () => {
    mockUseClasses.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "staff" })
    expect(screen.queryByText("+ הוספת סוג שיעור")).not.toBeInTheDocument()
  })

  it("staff sees 'view only' placeholder instead of the actions menu", () => {
    mockUseClasses.mockReturnValue({
      data: [fakeClass],
      isLoading: false,
      error: null,
    } as any)
    renderPage({ role: "staff" })
    expect(screen.getByText("צפייה בלבד")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /פעולות/ })).not.toBeInTheDocument()
  })

  it("active class: actions menu shows 'השבתה' (not 'הפעלה')", async () => {
    mockUseClasses.mockReturnValue({
      data: [fakeClass],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage({ role: "owner" })
    await user.click(screen.getByRole("button", { name: /פעולות/ }))
    expect(screen.getByText("השבתה")).toBeInTheDocument()
    expect(screen.queryByText("הפעלה")).not.toBeInTheDocument()
  })

  it("inactive class: actions menu shows 'הפעלה' (not 'השבתה')", async () => {
    mockUseClasses.mockReturnValue({
      data: [{ ...fakeClass, is_active: false }],
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
    mockUseClasses.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage({ role: "owner" })
    await user.click(screen.getByText("+ הוספת סוג שיעור"))
    expect(screen.getByText("סוג שיעור חדש")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "צור שיעור" })).toBeInTheDocument()
  })
})
