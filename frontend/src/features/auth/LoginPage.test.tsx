import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import LoginPage from "./LoginPage"

// Mock the auth api
vi.mock("./api", () => ({
  login: vi.fn(),
}))

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
  localStorage.clear()
})

describe("LoginPage", () => {
  it("renders the login form", () => {
    renderLogin()
    expect(screen.getByText("DopaCRM")).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toBeInTheDocument()
    expect(screen.getByLabelText("Password")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()
  })

  it("stores token and navigates on successful login", async () => {
    const user = userEvent.setup()
    mockLogin.mockResolvedValue({
      access_token: "jwt-123",
      token_type: "bearer",
      expires_in: 28800,
    })

    renderLogin()
    await user.type(screen.getByLabelText("Email"), "admin@dopacrm.com")
    await user.type(screen.getByLabelText("Password"), "Admin@12345")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(mockLogin).toHaveBeenCalledWith({
      email: "admin@dopacrm.com",
      password: "Admin@12345",
    })
    expect(localStorage.getItem("token")).toBe("jwt-123")
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard")
  })

  it("shows error message on failed login", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new Error("Invalid credentials"))

    renderLogin()
    await user.type(screen.getByLabelText("Email"), "bad@email.com")
    await user.type(screen.getByLabelText("Password"), "wrong")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument()
    expect(localStorage.getItem("token")).toBeNull()
  })

  it("shows loading state while submitting", async () => {
    const user = userEvent.setup()
    // Never resolve — keeps the form in loading state
    mockLogin.mockReturnValue(new Promise(() => {}))

    renderLogin()
    await user.type(screen.getByLabelText("Email"), "admin@dopacrm.com")
    await user.type(screen.getByLabelText("Password"), "Admin@12345")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(screen.getByRole("button", { name: "Signing in..." })).toBeDisabled()
  })
})
