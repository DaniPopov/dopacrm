import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import ClassDetailPage from "./ClassDetailPage"
import type { GymClass } from "./types"

/**
 * ClassDetailPage — /classes/:id.
 *
 * Covers:
 * - Loading
 * - Error + fallback "השיעור לא נמצא" when data is undefined
 * - Renders header + edit form when the fetch resolves
 * - Submit → useUpdateClass.mutate called with {id, data}; navigate on success
 * - Cancel → navigate back without mutating
 * - Back link (← חזרה לרשימה) navigates to /classes
 * - Mutation error runs through humanizeClassError
 */

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  )
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: "c1" }),
  }
})

vi.mock("./hooks", () => ({
  useClass: vi.fn(),
  useUpdateClass: vi.fn(),
}))

// The Coaches section is covered by its own tests; stub it so this
// suite stays focused on the class-edit flow.
vi.mock("@/features/coaches/ClassCoachesSection", () => ({
  default: () => null,
}))

import { useClass, useUpdateClass } from "./hooks"
const mockUseClass = vi.mocked(useClass)
const mockUseUpdateClass = vi.mocked(useUpdateClass)

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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ClassDetailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("ClassDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseUpdateClass.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
  })

  it("shows loading while fetching", () => {
    mockUseClass.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows an error when the fetch fails", () => {
    mockUseClass.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("boom"),
    } as any)
    renderPage()
    expect(screen.getByText("boom")).toBeInTheDocument()
  })

  it("falls back to Hebrew 'not found' when error has no message", () => {
    mockUseClass.mockReturnValue({ data: undefined, isLoading: false, error: null } as any)
    renderPage()
    expect(screen.getByText("השיעור לא נמצא")).toBeInTheDocument()
  })

  it("renders header + form when the class loads", () => {
    mockUseClass.mockReturnValue({
      data: fakeClass,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("עריכת Spinning")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "שמור שינויים" })).toBeInTheDocument()
  })

  it("submit calls mutate with {id, data} and navigates on success", async () => {
    const mutate = vi.fn((_args, opts) => opts?.onSuccess?.())
    mockUseUpdateClass.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUseClass.mockReturnValue({
      data: fakeClass,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(mutate).toHaveBeenCalledTimes(1)
    const [args] = mutate.mock.calls[0]
    expect(args.id).toBe("c1")
    expect(args.data.name).toBe("Spinning")
    expect(mockNavigate).toHaveBeenCalledWith("/classes")
  })

  it("cancel navigates back without mutating", async () => {
    const mutate = vi.fn()
    mockUseUpdateClass.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUseClass.mockReturnValue({
      data: fakeClass,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "ביטול" }))

    expect(mutate).not.toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith("/classes")
  })

  it("back-link navigates to /classes", async () => {
    mockUseClass.mockReturnValue({
      data: fakeClass,
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("← חזרה לרשימה"))
    expect(mockNavigate).toHaveBeenCalledWith("/classes")
  })

  it("mutation error surfaces through humanizeClassError (409 → phrase in Hebrew)", () => {
    mockUseUpdateClass.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: Object.assign(new Error("dup"), { status: 409 }),
    } as any)
    mockUseClass.mockReturnValue({
      data: fakeClass,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("שיעור בשם זה כבר קיים בחדר הכושר")).toBeInTheDocument()
  })
})
