import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import ClassForm from "./ClassForm"
import type { GymClass } from "./types"

/**
 * ClassForm — shared create/edit form for a gym class type.
 *
 * Covers:
 * - Required name field, Hebrew-friendly placeholders
 * - Submit normalizes empty optional fields to null
 * - Preset color palette: click → color set on the form
 * - "Clear" button resets color
 * - Edit mode prefills name + description + selected preset
 * - Error prop renders above the buttons
 * - Submit button respects the `submitting` prop
 */

const fakeClass: GymClass = {
  id: "c1",
  tenant_id: "t1",
  name: "ספינינג",
  description: "רכיבה עצים בפנים",
  color: "#3B82F6", // matches the "כחול" preset
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

  it("submits with the typed values, normalizing empty optional fields to null", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <ClassForm submitLabel="צור שיעור" onSubmit={onSubmit} onCancel={vi.fn()} />,
    )

    // Name is now the only visible text input (color is a picker).
    const nameInput = container.querySelector('input[type="text"]') as HTMLInputElement
    await user.type(nameInput, "יוגה")

    await user.click(screen.getByRole("button", { name: "צור שיעור" }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toEqual({
      name: "יוגה",
      description: null,
      color: null,
    })
  })

  it("clicking a preset color swatch sets it on submit", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <ClassForm submitLabel="צור שיעור" onSubmit={onSubmit} onCancel={vi.fn()} />,
    )

    await user.click(screen.getByRole("button", { name: "כחול" }))
    expect(container.textContent).toContain("#3B82F6")

    const nameInput = container.querySelector('input[type="text"]') as HTMLInputElement
    await user.type(nameInput, "ספינינג")
    await user.click(screen.getByRole("button", { name: "צור שיעור" }))

    expect(onSubmit.mock.calls[0][0].color).toBe("#3B82F6")
  })

  it("clear button resets the selected color", async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ClassForm submitLabel="צור שיעור" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    )

    await user.click(screen.getByRole("button", { name: "כחול" }))
    expect(container.textContent).toContain("#3B82F6")

    await user.click(screen.getByRole("button", { name: "נקה צבע" }))
    expect(container.textContent).toContain("לא נבחר צבע")
  })

  it("palette shows every preset label", () => {
    render(
      <ClassForm submitLabel="צור שיעור" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    )
    // Spot-check a few Hebrew preset labels
    for (const label of ["כחול", "ירוק", "אדום", "סגול", "אפור"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument()
    }
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
  it("prefills name + description, and the matching preset is marked selected", () => {
    const { container } = render(
      <ClassForm
        initial={fakeClass}
        submitLabel="שמור שינויים"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const nameInput = container.querySelector('input[type="text"]') as HTMLInputElement
    expect(nameInput.value).toBe("ספינינג")
    expect((container.querySelector("textarea") as HTMLTextAreaElement).value).toBe(
      "רכיבה עצים בפנים",
    )
    // Selected preset shows the color hex in the "נבחר:" line
    expect(container.textContent).toContain("#3B82F6")
    // And has aria-pressed=true
    expect(screen.getByRole("button", { name: "כחול" })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
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
