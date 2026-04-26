import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { SessionCard } from "./SessionCard"
import type { ClassSession } from "./types"

const baseSession: ClassSession = {
  id: "s1",
  tenant_id: "t1",
  class_id: "c1",
  template_id: "tpl1",
  starts_at: "2026-05-19T15:00:00Z",
  ends_at: "2026-05-19T16:00:00Z",
  head_coach_id: "k1",
  assistant_coach_id: null,
  status: "scheduled",
  is_customized: false,
  cancelled_at: null,
  cancelled_by: null,
  cancellation_reason: null,
  notes: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
}

describe("SessionCard", () => {
  it("renders class + coach name", () => {
    render(
      <SessionCard
        session={baseSession}
        className="Boxing"
        classColor="#3B82F6"
        coachName="David Cohen"
        onClick={() => {}}
      />,
    )
    expect(screen.getByText("Boxing")).toBeInTheDocument()
    expect(screen.getByText("David Cohen")).toBeInTheDocument()
  })

  it("shows ad-hoc star badge when no template", () => {
    render(
      <SessionCard
        session={{ ...baseSession, template_id: null }}
        className="Boxing"
        classColor={null}
        coachName="A"
        onClick={() => {}}
      />,
    )
    expect(screen.getByText("★")).toBeInTheDocument()
  })

  it("does not show ad-hoc badge for template-backed sessions", () => {
    render(
      <SessionCard
        session={baseSession}
        className="Boxing"
        classColor={null}
        coachName="A"
        onClick={() => {}}
      />,
    )
    expect(screen.queryByText("★")).not.toBeInTheDocument()
  })

  it("renders cancelled state with strike + 🚫", () => {
    render(
      <SessionCard
        session={{
          ...baseSession,
          status: "cancelled",
          cancelled_at: "2026-05-19T10:00:00Z",
        }}
        className="Boxing"
        classColor="#3B82F6"
        coachName="David"
        onClick={() => {}}
      />,
    )
    expect(screen.getByLabelText("cancelled")).toBeInTheDocument()
  })

  it("renders fallback when coach is null", () => {
    render(
      <SessionCard
        session={{ ...baseSession, head_coach_id: null }}
        className="Boxing"
        classColor={null}
        coachName={null}
        onClick={() => {}}
      />,
    )
    expect(screen.getByText("ללא מאמן")).toBeInTheDocument()
  })

  it("calls onClick when activated", async () => {
    const onClick = vi.fn()
    render(
      <SessionCard
        session={baseSession}
        className="Boxing"
        classColor={null}
        coachName="A"
        onClick={onClick}
      />,
    )
    await userEvent.click(screen.getByRole("button"))
    expect(onClick).toHaveBeenCalledOnce()
  })
})
