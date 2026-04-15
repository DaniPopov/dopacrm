import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import MemberForm from "./MemberForm"
import type { Member } from "./types"

/**
 * Shared member create/edit form.
 *
 * Tested behaviors:
 * - Creates mode (no initial): all fields render, defaults are empty,
 *   onSubmit fires with the typed values, cancel fires onCancel.
 * - Edit mode (initial=<member>): fields prefill with the member's data.
 * - Error display: Hebrew error message shows when passed.
 * - Submit button label is configurable.
 */

const fakeMember: Member = {
  id: "m1",
  tenant_id: "t1",
  first_name: "Dana",
  last_name: "Cohen",
  phone: "+972-50-111-2222",
  email: "dana@example.com",
  date_of_birth: "1990-05-15",
  gender: "female",
  status: "active",
  join_date: "2026-01-01",
  frozen_at: null,
  frozen_until: null,
  cancelled_at: null,
  notes: "Prefers mornings",
  custom_fields: {},
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

describe("MemberForm — create mode", () => {
  it("renders the required-field stars on first_name, last_name, phone", () => {
    render(
      <MemberForm
        submitLabel="צור מנוי"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText("שם פרטי *")).toBeInTheDocument()
    expect(screen.getByText("שם משפחה *")).toBeInTheDocument()
    expect(screen.getByText("טלפון *")).toBeInTheDocument()
  })

  it("shows the configurable submit label", () => {
    render(
      <MemberForm submitLabel="צור מנוי" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    )
    expect(screen.getByRole("button", { name: "צור מנוי" })).toBeInTheDocument()
  })

  it("submits with the values the user typed", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <MemberForm submitLabel="צור מנוי" onSubmit={onSubmit} onCancel={vi.fn()} />,
    )

    // Required text fields
    await user.type(container.querySelector('input[type="text"]')!, "Dana")
    // Second text input (last name)
    const textInputs = container.querySelectorAll('input[type="text"]')
    await user.type(textInputs[1], "Cohen")
    await user.type(container.querySelector('input[type="tel"]')!, "+972-50-1")

    await user.click(screen.getByRole("button", { name: "צור מנוי" }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const submitted = onSubmit.mock.calls[0][0]
    expect(submitted.first_name).toBe("Dana")
    expect(submitted.last_name).toBe("Cohen")
    expect(submitted.phone).toBe("+972-50-1")
  })

  it("cancel button calls onCancel without submitting", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    render(
      <MemberForm submitLabel="צור מנוי" onSubmit={onSubmit} onCancel={onCancel} />,
    )
    await user.click(screen.getByRole("button", { name: "ביטול" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("disables submit while submitting=true", () => {
    render(
      <MemberForm
        submitting
        submitLabel="צור מנוי"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const btn = screen.getByRole("button", { name: "שומר..." })
    expect(btn).toBeDisabled()
  })
})

describe("MemberForm — edit mode", () => {
  it("prefills every field from `initial`", () => {
    const { container } = render(
      <MemberForm
        initial={fakeMember}
        submitLabel="שמור שינויים"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const textInputs = container.querySelectorAll('input[type="text"]')
    expect((textInputs[0] as HTMLInputElement).value).toBe("Dana")
    expect((textInputs[1] as HTMLInputElement).value).toBe("Cohen")
    expect((container.querySelector('input[type="tel"]') as HTMLInputElement).value).toBe(
      "+972-50-111-2222",
    )
    expect((container.querySelector('input[type="email"]') as HTMLInputElement).value).toBe(
      "dana@example.com",
    )
    expect((container.querySelector("textarea") as HTMLTextAreaElement).value).toBe(
      "Prefers mornings",
    )
  })

  it("submits edited values back with the same shape", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const { container } = render(
      <MemberForm
        initial={fakeMember}
        submitLabel="שמור שינויים"
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    )
    const notesTextarea = container.querySelector("textarea") as HTMLTextAreaElement
    await user.clear(notesTextarea)
    await user.type(notesTextarea, "Now prefers evenings")

    await user.click(screen.getByRole("button", { name: "שמור שינויים" }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const submitted = onSubmit.mock.calls[0][0]
    expect(submitted.notes).toBe("Now prefers evenings")
    // Other fields untouched
    expect(submitted.first_name).toBe("Dana")
    expect(submitted.phone).toBe("+972-50-111-2222")
  })
})

describe("MemberForm — error display", () => {
  it("renders the Hebrew error message when `error` is set", () => {
    render(
      <MemberForm
        error="מנוי עם מספר טלפון זה כבר קיים"
        submitLabel="צור מנוי"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText("מנוי עם מספר טלפון זה כבר קיים")).toBeInTheDocument()
  })

  it("does not render the error block when error is null", () => {
    render(
      <MemberForm
        error={null}
        submitLabel="צור מנוי"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    // No red error container should exist
    expect(screen.queryByText(/שגיאה/i)).not.toBeInTheDocument()
  })
})
