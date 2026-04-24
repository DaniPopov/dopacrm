import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import CoachForm from "./CoachForm"

describe("CoachForm", () => {
  it("renders empty when no initial values", () => {
    const { container } = render(
      <CoachForm submitLabel="Save" onSubmit={() => {}} onCancel={() => {}} />,
    )
    const textInputs = container.querySelectorAll('input[type="text"]')
    expect((textInputs[0] as HTMLInputElement).value).toBe("")
    expect((textInputs[1] as HTMLInputElement).value).toBe("")
  })

  it("submit calls onSubmit with trimmed values + null for empty optional", async () => {
    const onSubmit = vi.fn()
    const { container } = render(
      <CoachForm
        submitLabel="Save"
        onSubmit={onSubmit}
        onCancel={() => {}}
      />,
    )
    const user = userEvent.setup()
    const textInputs = container.querySelectorAll('input[type="text"]')
    await user.type(textInputs[0] as HTMLInputElement, "  David  ")
    await user.type(textInputs[1] as HTMLInputElement, "Cohen")
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(onSubmit).toHaveBeenCalledWith({
      first_name: "David",
      last_name: "Cohen",
      phone: null,
      email: null,
    })
  })

  it("pre-fills from initial values", () => {
    const { container } = render(
      <CoachForm
        initial={{
          first_name: "Yoni",
          last_name: "Levi",
          phone: "0500",
          email: "y@gym.com",
        }}
        submitLabel="Save"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    const textInputs = container.querySelectorAll('input[type="text"]')
    expect((textInputs[0] as HTMLInputElement).value).toBe("Yoni")
    expect((textInputs[1] as HTMLInputElement).value).toBe("Levi")
    const phone = container.querySelector('input[type="tel"]') as HTMLInputElement
    expect(phone.value).toBe("0500")
    const email = container.querySelector('input[type="email"]') as HTMLInputElement
    expect(email.value).toBe("y@gym.com")
  })

  it("shows error when provided", () => {
    render(
      <CoachForm
        submitLabel="Save"
        error="שגיאה מהשרת"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByText("שגיאה מהשרת")).toBeInTheDocument()
  })

  it("cancel button triggers onCancel", async () => {
    const onCancel = vi.fn()
    render(
      <CoachForm
        submitLabel="Save"
        onSubmit={() => {}}
        onCancel={onCancel}
      />,
    )
    await userEvent.click(screen.getByRole("button", { name: "ביטול" }))
    expect(onCancel).toHaveBeenCalled()
  })
})
