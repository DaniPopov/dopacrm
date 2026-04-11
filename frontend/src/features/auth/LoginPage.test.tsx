import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import LoginPage from "./LoginPage"
import { LoginError } from "./api"

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api")
  return {
    ...actual,
    login: vi.fn(),
  }
})

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

async function submitLogin() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText("אימייל"), "test@example.com")
  await user.type(screen.getByLabelText("סיסמה"), "whatever")
  await user.click(screen.getByRole("button", { name: "התחברות" }))
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
    expect(mockAuthLogin).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard")
  })

  it("shows Hebrew wrong-credentials message on 401", async () => {
    mockLogin.mockRejectedValue(new LoginError("Invalid credentials", 401))
    renderLogin()
    await submitLogin()
    expect(await screen.findByText("שגיאה במייל או סיסמה")).toBeInTheDocument()
  })

  it("shows Hebrew rate-limit message on 429", async () => {
    mockLogin.mockRejectedValue(new LoginError("Rate limit", 429))
    renderLogin()
    await submitLogin()
    expect(
      await screen.findByText("יותר מדי ניסיונות, נסו שוב בעוד דקה"),
    ).toBeInTheDocument()
  })

  it("shows Hebrew system-error message on 500", async () => {
    mockLogin.mockRejectedValue(new LoginError("boom", 500))
    renderLogin()
    await submitLogin()
    expect(
      await screen.findByText("שגיאת מערכת, נסו שוב בעוד מספר רגעים"),
    ).toBeInTheDocument()
  })

  it("shows Hebrew network-error message on status 0", async () => {
    mockLogin.mockRejectedValue(new LoginError("network", 0))
    renderLogin()
    await submitLogin()
    expect(
      await screen.findByText("אין חיבור לשרת, בדקו את החיבור לאינטרנט"),
    ).toBeInTheDocument()
  })

  it("shows Hebrew forbidden message on 403", async () => {
    mockLogin.mockRejectedValue(new LoginError("Account suspended", 403))
    renderLogin()
    await submitLogin()
    expect(
      await screen.findByText("החשבון מושהה, פנו למנהל המערכת"),
    ).toBeInTheDocument()
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
