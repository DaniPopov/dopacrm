import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import EditUserDialog from "./EditUserDialog"
import type { User } from "./types"

/**
 * EditUserDialog test surface:
 * - Prefills all fields from the provided user
 * - Submits only the fields the user actually changed (shallow diff)
 * - Empty password field is NOT sent (keeps existing hash)
 * - Password field IS sent when filled
 * - Cancel / X / backdrop close the dialog without mutating
 * - Error from the mutation surfaces through humanizeUserError
 */

vi.mock("./hooks", () => ({
  useUpdateUser: vi.fn(),
}))

import { useUpdateUser } from "./hooks"
const mockUseUpdateUser = vi.mocked(useUpdateUser)

const fakeUser: User = {
  id: "u1",
  tenant_id: "t1",
  email: "dana@example.com",
  role: "staff",
  is_active: true,
  first_name: "Dana",
  last_name: "Cohen",
  phone: "+972-50-111",
  oauth_provider: null,
  created_at: "2026-04-14T12:00:00Z",
  updated_at: "2026-04-14T12:00:00Z",
}

function renderDialog(user: User = fakeUser, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <EditUserDialog user={user} tenantId="t1" onClose={onClose} />
    </QueryClientProvider>,
  )
}

describe("EditUserDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseUpdateUser.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
  })

  it("prefills every field from the user", () => {
    const { container } = renderDialog()
    expect(
      (container.querySelector('input[type="email"]') as HTMLInputElement).value,
    ).toBe("dana@example.com")
    expect(
      (container.querySelector('input[type="tel"]') as HTMLInputElement).value,
    ).toBe("+972-50-111")
    // first/last name are text inputs
    const texts = container.querySelectorAll('input[type="text"]')
    expect((texts[0] as HTMLInputElement).value).toBe("Dana")
    expect((texts[1] as HTMLInputElement).value).toBe("Cohen")
    // password empty by default
    expect(
      (container.querySelector('input[type="password"]') as HTMLInputElement).value,
    ).toBe("")
  })

  it("submits only the changed fields — password field empty → not sent", async () => {
    const mutate = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    const { container } = renderDialog()

    // Change only first_name
    const firstNameInput = container.querySelectorAll('input[type="text"]')[0] as HTMLInputElement
    await user.clear(firstNameInput)
    await user.type(firstNameInput, "Danielle")

    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(mutate).toHaveBeenCalledTimes(1)
    const [args] = mutate.mock.calls[0]
    expect(args.id).toBe("u1")
    expect(args.data).toEqual({ first_name: "Danielle" })
    // password NOT in patch because field was left empty
    expect(args.data.password).toBeUndefined()
  })

  it("sends password when the reset field is filled", async () => {
    const mutate = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    const { container } = renderDialog()

    const pwd = container.querySelector('input[type="password"]') as HTMLInputElement
    await user.type(pwd, "NewPass1!")
    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    const [args] = mutate.mock.calls[0]
    expect(args.data.password).toBe("NewPass1!")
  })

  it("closes without mutating if nothing changed", async () => {
    const mutate = vi.fn()
    const onClose = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderDialog(fakeUser, onClose)

    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(mutate).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it("cancel button fires onClose without mutating", async () => {
    const mutate = vi.fn()
    const onClose = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderDialog(fakeUser, onClose)

    await user.click(screen.getByRole("button", { name: "ביטול" }))

    expect(mutate).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it("X button fires onClose", async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderDialog(fakeUser, onClose)
    await user.click(screen.getByRole("button", { name: "סגירה" }))
    expect(onClose).toHaveBeenCalled()
  })

  it("renders Hebrew error from humanizeUserError when mutation fails (409)", () => {
    mockUseUpdateUser.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      error: Object.assign(new Error("dup"), { status: 409 }),
    } as any)
    renderDialog()
    expect(screen.getByText("משתמש עם מייל זה כבר קיים")).toBeInTheDocument()
  })

  it("disables submit while mutation is pending", () => {
    mockUseUpdateUser.mockReturnValue({
      mutate: vi.fn(),
      reset: vi.fn(),
      isPending: true,
      error: null,
    } as any)
    renderDialog()
    const btn = screen.getByRole("button", { name: "שומר..." })
    expect(btn).toBeDisabled()
  })

  it("can change the role via the role select", async () => {
    const mutate = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderDialog() // user.role = staff

    const roleSelect = screen.getByDisplayValue("צוות") // staff label
    await user.selectOptions(roleSelect, "owner")

    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))
    const [args] = mutate.mock.calls[0]
    expect(args.data.role).toBe("owner")
  })

  it("can toggle is_active via the status select", async () => {
    const mutate = vi.fn()
    mockUseUpdateUser.mockReturnValue({
      mutate,
      reset: vi.fn(),
      isPending: false,
      error: null,
    } as any)
    const user = userEvent.setup()
    renderDialog() // is_active = true

    const statusSelect = screen.getByDisplayValue("פעיל")
    await user.selectOptions(statusSelect, "disabled")

    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))
    const [args] = mutate.mock.calls[0]
    expect(args.data.is_active).toBe(false)
  })
})
