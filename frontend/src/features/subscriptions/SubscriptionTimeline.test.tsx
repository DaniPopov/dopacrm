import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import SubscriptionTimeline from "./SubscriptionTimeline"
import type { SubscriptionEvent } from "./types"

/**
 * Timeline renders Hebrew labels for each event type plus extra pills
 * for the noteworthy payloads: days_late on a late renewal, cancellation
 * reason, and the "אוטומטי" marker for system events (created_by=null).
 */

function ev(overrides: Partial<SubscriptionEvent>): SubscriptionEvent {
  // Explicit property check for created_by — ?? would replace an intentional
  // null (the "system event" sentinel) with "u1" and hide a real bug.
  const createdBy = "created_by" in overrides ? (overrides.created_by ?? null) : "u1"
  return {
    id: overrides.id ?? "e1",
    tenant_id: "t1",
    subscription_id: "s1",
    event_type: overrides.event_type ?? "created",
    event_data: overrides.event_data ?? {},
    occurred_at: overrides.occurred_at ?? "2026-04-17T12:00:00Z",
    created_by: createdBy,
  }
}

describe("SubscriptionTimeline", () => {
  it("shows empty message when there are no events", () => {
    render(<SubscriptionTimeline events={[]} />)
    expect(screen.getByText("אין אירועים")).toBeInTheDocument()
  })

  it("renders the Hebrew label for each event type", () => {
    render(
      <SubscriptionTimeline
        events={[
          ev({ id: "1", event_type: "created" }),
          ev({ id: "2", event_type: "frozen" }),
          ev({ id: "3", event_type: "cancelled" }),
        ]}
      />,
    )
    expect(screen.getByText("נפתח מנוי")).toBeInTheDocument()
    expect(screen.getByText("המנוי הוקפא")).toBeInTheDocument()
    expect(screen.getByText("המנוי בוטל")).toBeInTheDocument()
  })

  it("shows a days_late pill on a late renewal", () => {
    render(
      <SubscriptionTimeline
        events={[
          ev({ event_type: "renewed", event_data: { days_late: 3 } }),
        ]}
      />,
    )
    expect(screen.getByText("3 ימי איחור")).toBeInTheDocument()
  })

  it("does NOT show the late-renewal pill when days_late is 0", () => {
    render(
      <SubscriptionTimeline
        events={[
          ev({ event_type: "renewed", event_data: { days_late: 0 } }),
        ]}
      />,
    )
    expect(screen.queryByText(/ימי איחור/)).not.toBeInTheDocument()
  })

  it("maps cancellation reason keys to Hebrew labels", () => {
    render(
      <SubscriptionTimeline
        events={[
          ev({ event_type: "cancelled", event_data: { reason: "too_expensive" } }),
        ]}
      />,
    )
    expect(screen.getByText("יקר מדי")).toBeInTheDocument()
  })

  it("marks system events (created_by=null) with 'אוטומטי' pill", () => {
    render(
      <SubscriptionTimeline
        events={[ev({ event_type: "expired", created_by: null })]}
      />,
    )
    expect(screen.getByText("אוטומטי")).toBeInTheDocument()
  })
})
