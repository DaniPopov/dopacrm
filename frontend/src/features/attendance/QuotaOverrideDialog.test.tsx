import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import QuotaOverrideDialog from "./QuotaOverrideDialog"

describe("QuotaOverrideDialog", () => {
  it("renders Hebrew copy for quota_exceeded with the class name", () => {
    render(
      <QuotaOverrideDialog
        kind="quota_exceeded"
        className="יוגה"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText("המנוי במכסה מלאה")).toBeInTheDocument()
    expect(screen.getByText(/יוגה/)).toBeInTheDocument()
  })

  it("renders 'not in plan' copy for not_covered", () => {
    render(
      <QuotaOverrideDialog
        kind="not_covered"
        className="ספינינג"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText("שיעור לא כלול במסלול")).toBeInTheDocument()
  })

  it("confirms with null reason when staff leaves the field empty", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <QuotaOverrideDialog
        kind="quota_exceeded"
        className="יוגה"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )
    await user.click(screen.getByRole("button", { name: "אשר כניסה" }))
    expect(onConfirm).toHaveBeenCalledWith(null)
  })

  it("trims the reason on submit", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <QuotaOverrideDialog
        kind="quota_exceeded"
        className="יוגה"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )
    await user.type(screen.getByRole("textbox"), "  birthday class  ")
    await user.click(screen.getByRole("button", { name: "אשר כניסה" }))
    expect(onConfirm).toHaveBeenCalledWith("birthday class")
  })

  it("cancels via the footer button", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(
      <QuotaOverrideDialog
        kind="quota_exceeded"
        className="יוגה"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    await user.click(screen.getByRole("button", { name: "ביטול" }))
    expect(onCancel).toHaveBeenCalled()
  })

  it("disables the confirm button while submitting", () => {
    render(
      <QuotaOverrideDialog
        kind="quota_exceeded"
        className="יוגה"
        submitting
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: "שומר..." })).toBeDisabled()
  })
})
