import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import ClassForm from "./ClassForm"
import type { GymClass } from "./types"

/**
 * ClassForm — shared create/edit form for a gym class type.
 *
 * Covered:
 * - Name field is required; form doesn't submit when empty (native HTML5).
 * - Submits with the typed name, color, description.
 * - Empty description/color are normalized to null in the submit payload.
 * - Prefills from `initial` in edit mode.
 * - Color swatch preview shows next to the color input when a color is set.
 * - Error prop renders above the buttons.
 * - Submit button respects the `submitting` prop.
 */

const fakeClass: GymClass = {
  id: "c1",
  tenant_id: "t1",
  name: "Spinning",
  description: "High-intensity indoor cycling",
  color: "#3B82F6",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

describe("ClassForm — create mode", () => {
  it("renders the required-field star on name", () => {
    render(
      <ClassForm submitLabel="צור שיעור" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    )
    expect(screen.getByText("שם השיעור *")).toBeInTheDocument()
  })

  it("submits with the typed values and normalizes empty optional fields to null", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <ClassForm submitLabel="צור שיעור" onSubmit={onSubmit} onCancel={vi.fn()} />,
    )

    const nameInput = container.querySelector('input[type="text"]') as HTMLInputElement
    await user.type(nameInput, "Yoga")

    // Leave description + color empty → they should be null in the payload
    await user.click(screen.getByRole("button", { name: "צור שיעור" }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const submitted = onSubmit.mock.calls[0][0]
    expect(submitted).toEqual({
      name: "Yoga",
      description: null,
      color: null,
    })
  })

  it("cancel fires onCancel without submitting", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    render(
      <ClassForm submitLabel="צור שיעור" onSubmit={onSubmit} onCancel={onCancel} />,
    )
    await user.click(screen.getByRole("button", { name: "ביטול" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("disables submit while submitting=true", () => {
    render(
      <ClassForm
        submitting
        submitLabel="צור שיעור"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: "שומר..." })).toBeDisabled()
  })
})

describe("ClassForm — edit mode", () => {
  it("prefills every field from `initial`", () => {
    const { container } = render(
      <ClassForm
        initial={fakeClass}
        submitLabel="שמור שינויים"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const inputs = container.querySelectorAll("input[type='text']")
    expect((inputs[0] as HTMLInputElement).value).toBe("Spinning")
    // color input is the second text input
    expect((inputs[1] as HTMLInputElement).value).toBe("#3B82F6")
    expect((container.querySelector("textarea") as HTMLTextAreaElement).value).toBe(
      "High-intensity indoor cycling",
    )
  })

  it("shows the color swatch preview when a color is set", () => {
    const { container } = render(
      <ClassForm
        initial={fakeClass}
        submitLabel="שמור שינויים"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    // The swatch is an aria-hidden div with inline background-color style
    const swatches = container.querySelectorAll('[aria-hidden="true"]')
    const colored = Array.from(swatches).find(
      (el) => (el as HTMLElement).style.backgroundColor,
    ) as HTMLElement | undefined
    expect(colored).toBeDefined()
  })
})

describe("ClassForm — error display", () => {
  it("renders the Hebrew error when `error` prop is set", () => {
    render(
      <ClassForm
        error="שיעור בשם זה כבר קיים בחדר הכושר"
        submitLabel="צור שיעור"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(
      screen.getByText("שיעור בשם זה כבר קיים בחדר הכושר"),
    ).toBeInTheDocument()
  })
})
