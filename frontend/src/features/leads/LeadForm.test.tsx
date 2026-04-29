import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import LeadForm from "./LeadForm"

describe("LeadForm", () => {
  it("renders empty when no initial values", () => {
    render(
      <LeadForm
        submitting={false}
        error={null}
        submitLabel="צור ליד"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByRole("button", { name: "צור ליד" })).toBeInTheDocument()
  })

  it("submit calls onSubmit with trimmed values + null for empty optionals", async () => {
    const onSubmit = vi.fn()
    const { container } = render(
      <LeadForm
        submitting={false}
        error={null}
        submitLabel="שמור"
        onSubmit={onSubmit}
        onCancel={() => {}}
      />,
    )
    const user = userEvent.setup()
    const textInputs = container.querySelectorAll('input[type="text"]')
    await user.type(textInputs[0] as HTMLInputElement, "  Yael  ")
    await user.type(textInputs[1] as HTMLInputElement, "Cohen")
    const phone = container.querySelector('input[type="tel"]') as HTMLInputElement
    await user.type(phone, "+972-50-123")

    await user.click(screen.getByRole("button", { name: "שמור" }))
    expect(onSubmit).toHaveBeenCalledWith({
      first_name: "Yael",
      last_name: "Cohen",
      phone: "+972-50-123",
      email: null,
      source: "walk_in",
      notes: null,
    })
  })

  it("pre-fills from initial lead", () => {
    const lead = {
      id: "1",
      tenant_id: "t",
      first_name: "Maya",
      last_name: "Bar",
      phone: "+972-50-555-0001",
      email: "maya@x.co",
      source: "referral",
      status: "contacted",
      assigned_to: null,
      notes: "trial Tuesday",
      lost_reason: null,
      converted_member_id: null,
      custom_fields: {},
      created_at: "2026-04-01T00:00:00Z",
      updated_at: "2026-04-01T00:00:00Z",
    } as const

    const { container } = render(
      <LeadForm
        initial={lead}
        submitting={false}
        error={null}
        submitLabel="שמור"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    const textInputs = container.querySelectorAll('input[type="text"]')
    expect((textInputs[0] as HTMLInputElement).value).toBe("Maya")
    expect((textInputs[1] as HTMLInputElement).value).toBe("Bar")
    const phone = container.querySelector('input[type="tel"]') as HTMLInputElement
    expect(phone.value).toBe("+972-50-555-0001")
    const select = container.querySelector("select") as HTMLSelectElement
    expect(select.value).toBe("referral")
  })

  it("shows error message when supplied", () => {
    render(
      <LeadForm
        submitting={false}
        error="הפרטים שהוזנו אינם תקינים"
        submitLabel="שמור"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByText("הפרטים שהוזנו אינם תקינים")).toBeInTheDocument()
  })

  it("disables submit while submitting", () => {
    render(
      <LeadForm
        submitting={true}
        error={null}
        submitLabel="שמור"
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByRole("button", { name: "שומר..." })).toBeDisabled()
  })
})
