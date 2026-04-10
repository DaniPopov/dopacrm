import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import LandingPage from "./LandingPage"

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  )
}

describe("LandingPage", () => {
  it("renders Hebrew content", () => {
    renderLanding()
    expect(screen.getByText("מערכת ניהול חדר כושר")).toBeInTheDocument()
    expect(screen.getByText("כניסה לפורטל")).toBeInTheDocument()
  })

  it("renders all feature cards", () => {
    renderLanding()
    expect(screen.getByText("ניהול מנויים")).toBeInTheDocument()
    expect(screen.getByText("מעקב הכנסות")).toBeInTheDocument()
    expect(screen.getByText("ניהול לידים")).toBeInTheDocument()
    expect(screen.getByText("דשבורד חכם")).toBeInTheDocument()
  })

  it("navigates to login when portal button clicked", async () => {
    const user = userEvent.setup()
    renderLanding()
    await user.click(screen.getByText("כניסה לפורטל"))
    expect(mockNavigate).toHaveBeenCalledWith("/login")
  })

  it("navigates to login when CTA clicked", async () => {
    const user = userEvent.setup()
    renderLanding()
    await user.click(screen.getByText("התחילו עכשיו"))
    expect(mockNavigate).toHaveBeenCalledWith("/login")
  })

  it("shows Dopamineo in footer", () => {
    renderLanding()
    expect(screen.getByText(/Dopamineo/)).toBeInTheDocument()
  })
})
