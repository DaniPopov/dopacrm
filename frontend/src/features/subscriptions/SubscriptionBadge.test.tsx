import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { SubscriptionBadge } from "./SubscriptionBadge"

describe("SubscriptionBadge", () => {
  it.each([
    ["active", "פעיל"],
    ["frozen", "מוקפא"],
    ["expired", "פג תוקף"],
    ["cancelled", "בוטל"],
    ["replaced", "הוחלף"],
  ] as const)("renders Hebrew label for status=%s → %s", (status, label) => {
    render(<SubscriptionBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
