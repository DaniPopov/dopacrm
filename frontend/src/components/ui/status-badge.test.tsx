import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { StatusBadge } from "./status-badge"

describe("StatusBadge", () => {
  it.each([
    ["success", "emerald"],
    ["warning", "amber"],
    ["danger", "red"],
    ["neutral", "slate"],
    ["info", "indigo"],
    ["primary", "blue"],
  ] as const)("variant=%s gets the %s palette", (variant, palette) => {
    const { container } = render(<StatusBadge variant={variant}>x</StatusBadge>)
    const span = container.querySelector("span")!
    expect(span.className).toContain(palette)
  })

  it("renders its children as the label", () => {
    render(<StatusBadge variant="success">פעיל</StatusBadge>)
    expect(screen.getByText("פעיל")).toBeInTheDocument()
  })
})
