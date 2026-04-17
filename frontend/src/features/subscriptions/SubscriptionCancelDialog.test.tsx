import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import SubscriptionCancelDialog from "./SubscriptionCancelDialog"

vi.mock("./hooks", () => ({
  useCancelSubscription: vi.fn(),
}))

import { useCancelSubscription } from "./hooks"
const mockUseCancel = vi.mocked(useCancelSubscription)

describe("SubscriptionCancelDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("submits with reason + detail when staff fills the form", async () => {
    const mutate = vi.fn()
    mockUseCancel.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    render(<SubscriptionCancelDialog subscriptionId="s1" onClose={vi.fn()} />)

    await user.selectOptions(screen.getByRole("combobox"), "too_expensive")
    await user.type(screen.getByRole("textbox"), "switching gyms")
    await user.click(screen.getByRole("button", { name: "בטל מנוי" }))

    expect(mutate).toHaveBeenCalledTimes(1)
    const [args] = mutate.mock.calls[0]
    expect(args.id).toBe("s1")
    expect(args.data).toEqual({ reason: "too_expensive", detail: "switching gyms" })
  })

  it("submits with null reason + null detail when both are left empty", async () => {
    const mutate = vi.fn()
    mockUseCancel.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)

    const user = userEvent.setup()
    render(<SubscriptionCancelDialog subscriptionId="s1" onClose={vi.fn()} />)
    await user.click(screen.getByRole("button", { name: "בטל מנוי" }))

    expect(mutate).toHaveBeenCalled()
    const [args] = mutate.mock.calls[0]
    expect(args.data).toEqual({ reason: null, detail: null })
  })

  it("shows the Hebrew destructive warning copy", () => {
    mockUseCancel.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    render(<SubscriptionCancelDialog subscriptionId="s1" onClose={vi.fn()} />)
    expect(screen.getByText(/פעולה זו סופית/)).toBeInTheDocument()
  })

  it("disables the submit button while the mutation is in flight", () => {
    mockUseCancel.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: true,
      error: null,
    } as any)
    render(<SubscriptionCancelDialog subscriptionId="s1" onClose={vi.fn()} />)
    expect(screen.getByRole("button", { name: "שומר..." })).toBeDisabled()
  })

  it("renders the humanized error from a 409", () => {
    mockUseCancel.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: Object.assign(new Error("invalid transition"), { status: 409 }),
    } as any)
    render(<SubscriptionCancelDialog subscriptionId="s1" onClose={vi.fn()} />)
    expect(
      screen.getByText("לא ניתן לבצע פעולה זו בסטטוס הנוכחי"),
    ).toBeInTheDocument()
  })
})
