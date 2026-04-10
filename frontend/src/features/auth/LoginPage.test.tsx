import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import LoginPage from "./LoginPage"

vi.mock("./api", () => ({
  login: vi.fn(),
}))

vi.mock("./auth-provider", () => ({
  useAuth: () => ({ login: mockAuthLogin }),
}))

const mockAuthLogin = vi.fn()

import { login } from "./api"
const mockLogin = vi.mocked(login)

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("LoginPage", () => {
  it("renders the login form in Hebrew", () => {
    renderLogin()
    expect(screen.getByText("כניסה לפורטל")).toBeInTheDocument()
    expect(screen.getByLabelText("אימייל")).toBeInTheDocument()
    expect(screen.getByLabelText("סיסמה")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "התחברות" })).toBeInTheDocument()
  })

  it("calls login API and refreshes auth on success", async () => {
    const user = userEvent.setup()
    mockLogin.mockResolvedValue({
      access_token: "jwt-123",
      token_type: "bearer",
      expires_in: 28800,
    })
    mockAuthLogin.mockResolvedValue(undefined)

    renderLogin()
    await user.type(screen.getByLabelText("אימייל"), "admin@dopacrm.com")
    await user.type(screen.getByLabelText("סיסמה"), "Admin@12345")
    await user.click(screen.getByRole("button", { name: "התחברות" }))

    expect(mockLogin).toHaveBeenCalledWith({
      email: "admin@dopacrm.com",
      password: "Admin@12345",
    })
    // No localStorage — cookie is set by browser
    expect(mockAuthLogin).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard")
  })

  it("shows error message on failed login", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new Error("Invalid credentials"))

    renderLogin()
    await user.type(screen.getByLabelText("אימייל"), "bad@email.com")
    await user.type(screen.getByLabelText("סיסמה"), "wrong")
    await user.click(screen.getByRole("button", { name: "התחברות" }))

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument()
  })

  it("shows loading state while submitting", async () => {
    const user = userEvent.setup()
    mockLogin.mockReturnValue(new Promise(() => {}))

    renderLogin()
    await user.type(screen.getByLabelText("אימייל"), "admin@dopacrm.com")
    await user.type(screen.getByLabelText("סיסמה"), "Admin@12345")
    await user.click(screen.getByRole("button", { name: "התחברות" }))

    expect(screen.getByRole("button", { name: "מתחבר..." })).toBeDisabled()
  })

  it("has link back to landing page", () => {
    renderLogin()
    expect(screen.getByText("חזרה לעמוד הראשי")).toBeInTheDocument()
  })

  it("shows brand logo", () => {
    renderLogin()
    expect(screen.getByAltText("DopaCRM")).toBeInTheDocument()
  })
})
