import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { WeekdaysPicker } from "./WeekdaysPicker"

describe("WeekdaysPicker", () => {
  it("renders all 7 days", () => {
    render(<WeekdaysPicker value={[]} onChange={() => {}} />)
    for (const letter of ["א", "ב", "ג", "ד", "ה", "ו", "ש"]) {
      expect(screen.getByLabelText(`יום ${letter}`)).toBeInTheDocument()
    }
  })

  it("shows 'all days' hint when nothing selected", () => {
    render(<WeekdaysPicker value={[]} onChange={() => {}} />)
    expect(screen.getByText("כל הימים")).toBeInTheDocument()
  })

  it("toggles a day in via onChange", async () => {
    const onChange = vi.fn()
    render(<WeekdaysPicker value={[]} onChange={onChange} />)
    await userEvent.click(screen.getByLabelText("יום א"))
    expect(onChange).toHaveBeenCalledWith(["sun"])
  })

  it("toggles an already-selected day out", async () => {
    const onChange = vi.fn()
    render(<WeekdaysPicker value={["sun", "tue"]} onChange={onChange} />)
    await userEvent.click(screen.getByLabelText("יום א"))
    expect(onChange).toHaveBeenCalledWith(["tue"])
  })

  it("shows count when some days selected", () => {
    render(<WeekdaysPicker value={["sun", "tue"]} onChange={() => {}} />)
    expect(screen.getByText("2 ימים נבחרו")).toBeInTheDocument()
  })

  it("disabled state blocks clicks", async () => {
    const onChange = vi.fn()
    render(<WeekdaysPicker value={[]} onChange={onChange} disabled />)
    await userEvent.click(screen.getByLabelText("יום א"))
    expect(onChange).not.toHaveBeenCalled()
  })
})
