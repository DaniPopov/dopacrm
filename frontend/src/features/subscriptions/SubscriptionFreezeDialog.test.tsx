import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import SubscriptionFreezeDialog from "./SubscriptionFreezeDialog"

vi.mock("./hooks", () => ({
  useFreezeSubscription: vi.fn(),
}))

import { useFreezeSubscription } from "./hooks"
const mockUseFreeze = vi.mocked(useFreezeSubscription)

describe("SubscriptionFreezeDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseFreeze.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
  })

  it("submits with frozen_until=null for an open-ended freeze", async () => {
    const mutate = vi.fn()
    mockUseFreeze.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    render(<SubscriptionFreezeDialog subscriptionId="s1" onClose={vi.fn()} />)
    await user.click(screen.getByRole("button", { name: "הקפא" }))
    expect(mutate).toHaveBeenCalled()
    expect(mutate.mock.calls[0][0]).toEqual({
      id: "s1",
      data: { frozen_until: null },
    })
  })

  it("submits with the picked frozen_until date", async () => {
    const mutate = vi.fn()
    mockUseFreeze.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    const { container } = render(
      <SubscriptionFreezeDialog subscriptionId="s1" onClose={vi.fn()} />,
    )
    const dateInput = container.querySelector('input[type="date"]') as HTMLInputElement
    await user.type(dateInput, "2026-05-01")
    await user.click(screen.getByRole("button", { name: "הקפא" }))

    expect(mutate.mock.calls[0][0].data.frozen_until).toBe("2026-05-01")
  })

  it("cancels without calling the mutation", async () => {
    const mutate = vi.fn()
    mockUseFreeze.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<SubscriptionFreezeDialog subscriptionId="s1" onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "ביטול" }))
    expect(mutate).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })
})
