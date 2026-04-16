import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import PasswordInput from "./password-input"

/**
 * PasswordInput is a drop-in replacement for <input type="password">
 * with an eye toggle. Tests verify the masking behavior and the
 * toggle button accessibility.
 */

describe("PasswordInput", () => {
  it("renders as a masked input by default", () => {
    const { container } = render(<PasswordInput defaultValue="secret" />)
    const input = container.querySelector("input") as HTMLInputElement
    expect(input.type).toBe("password")
    expect(input.value).toBe("secret")
  })

  it("toggle button reveals the password when clicked", async () => {
    const user = userEvent.setup()
    const { container } = render(<PasswordInput defaultValue="secret" />)
    const input = container.querySelector("input") as HTMLInputElement
    expect(input.type).toBe("password")

    await user.click(screen.getByRole("button", { name: "הצג סיסמה" }))
    expect(input.type).toBe("text")
    // Button label flipped
    expect(screen.getByRole("button", { name: "הסתר סיסמה" })).toBeInTheDocument()
  })

  it("toggle button masks the password again when clicked twice", async () => {
    const user = userEvent.setup()
    const { container } = render(<PasswordInput defaultValue="secret" />)
    const input = container.querySelector("input") as HTMLInputElement
    await user.click(screen.getByRole("button", { name: "הצג סיסמה" }))
    expect(input.type).toBe("text")
    await user.click(screen.getByRole("button", { name: "הסתר סיסמה" }))
    expect(input.type).toBe("password")
  })

  it("forwards standard input props (value, onChange, required, placeholder)", async () => {
    const handleChange = (value: string): void => {
      capturedValue = value
    }
    let capturedValue = ""

    const user = userEvent.setup()
    const { container } = render(
      <PasswordInput
        placeholder="enter password"
        required
        onChange={(e) => handleChange(e.target.value)}
      />,
    )

    const input = container.querySelector("input") as HTMLInputElement
    expect(input.placeholder).toBe("enter password")
    expect(input.required).toBe(true)

    await user.type(input, "abc123")
    expect(capturedValue).toBe("abc123")
  })

  it("toggle button is skipped by tab navigation (tabIndex=-1)", () => {
    render(<PasswordInput />)
    const toggle = screen.getByRole("button", { name: "הצג סיסמה" })
    expect(toggle.getAttribute("tabindex")).toBe("-1")
  })

  it("merges caller className without breaking toggle positioning", () => {
    const { container } = render(
      <PasswordInput className="my-custom-class rounded-full" defaultValue="x" />,
    )
    const input = container.querySelector("input") as HTMLInputElement
    expect(input.className).toContain("my-custom-class")
    expect(input.className).toContain("rounded-full")
    // pl-10 is always added for the icon space
    expect(input.className).toContain("pl-10")
  })
})
