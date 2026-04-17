import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import MemberDetailPage from "./MemberDetailPage"
import type { Member } from "./types"

/**
 * Member edit page — /members/:id.
 *
 * Tested behaviors:
 * - Loading state
 * - Error state (member not found)
 * - Renders form prefilled when the fetch succeeds
 * - Submitting the form calls useUpdateMember and navigates back
 * - Cancel button navigates back without mutating
 * - Back link (← חזרה לרשימה) navigates back
 */

// ── Mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: "m1" }),
  }
})

vi.mock("./hooks", () => ({
  useMember: vi.fn(),
  useUpdateMember: vi.fn(),
}))

// The subscriptions section has its own tests + pulls in a lot of
// providers (auth, plans query). For this file — which tests the
// identity form — stub it to keep the surface focused.
vi.mock("@/features/subscriptions/MemberSubscriptionSection", () => ({
  default: () => null,
}))

import { useMember, useUpdateMember } from "./hooks"
const mockUseMember = vi.mocked(useMember)
const mockUseUpdateMember = vi.mocked(useUpdateMember)

// ── Fixtures ──────────────────────────────────────────────────────────

const fakeMember: Member = {
  id: "m1",
  tenant_id: "t1",
  first_name: "Dana",
  last_name: "Cohen",
  phone: "+972-50-111-2222",
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
        <MemberDetailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ── Tests ─────────────────────────────────────────────────────────────

describe("MemberDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: no in-flight mutation
    mockUseUpdateMember.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
  })

  it("shows loading while fetching", () => {
    mockUseMember.mockReturnValue({ data: undefined, isLoading: true, error: null } as any)
    renderPage()
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("shows an error message when the member cannot be fetched", () => {
    mockUseMember.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("not found"),
    } as any)
    renderPage()
    expect(screen.getByText("not found")).toBeInTheDocument()
    expect(screen.getByText("← חזרה לרשימה")).toBeInTheDocument()
  })

  it("falls back to Hebrew 'not found' message when error has no message", () => {
    mockUseMember.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("המנוי לא נמצא")).toBeInTheDocument()
  })

  it("renders header + form when the member loads", () => {
    mockUseMember.mockReturnValue({
      data: fakeMember,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    expect(screen.getByText("Dana Cohen")).toBeInTheDocument()
    expect(screen.getByText("+972-50-111-2222")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "שמור שינויים" })).toBeInTheDocument()
  })

  it("submits with the member id and stays on the page on success", async () => {
    // After shipping subscriptions, save keeps the user on the detail
    // page so they can proceed to the sub section below. Previously we
    // navigated to /members; the new behavior is intentional.
    const mutate = vi.fn((_args, opts) => opts?.onSuccess?.())
    mockUseUpdateMember.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUseMember.mockReturnValue({
      data: fakeMember,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(mutate).toHaveBeenCalledTimes(1)
    const [args] = mutate.mock.calls[0]
    expect(args.id).toBe("m1")
    expect(args.data.first_name).toBe("Dana")
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it("cancel navigates back without calling the mutation", async () => {
    const mutate = vi.fn()
    mockUseUpdateMember.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    mockUseMember.mockReturnValue({
      data: fakeMember,
      isLoading: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole("button", { name: "ביטול" }))

    expect(mutate).not.toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith("/members")
  })

  it("clicking the back link navigates to /members", async () => {
    mockUseMember.mockReturnValue({
      data: fakeMember,
      isLoading: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByText("← חזרה לרשימה"))
    expect(mockNavigate).toHaveBeenCalledWith("/members")
  })

  it("humanizes a mutation error and passes it to the form", () => {
    mockUseUpdateMember.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      // ApiError-ish shape the humanizer understands (status=422)
      error: Object.assign(new Error("invalid"), { status: 422 }),
    } as any)
    mockUseMember.mockReturnValue({
      data: fakeMember,
      isLoading: false,
      error: null,
    } as any)
    renderPage()
    // humanizeMemberError(422) → "הפרטים שהוזנו אינם תקינים, בדקו את הטופס"
    expect(
      screen.getByText("הפרטים שהוזנו אינם תקינים, בדקו את הטופס"),
    ).toBeInTheDocument()
  })
})
