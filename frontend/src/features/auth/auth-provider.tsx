import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { useNavigate } from "react-router-dom"
import { getMe, logout as apiLogout } from "./api"
import type { User } from "./types"

interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      setIsLoading(false)
      return
    }

    getMe()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("token")
      })
      .finally(() => setIsLoading(false))
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // Server logout failed — clear locally anyway
    }
    localStorage.removeItem("token")
    setUser(null)
    navigate("/login")
  }, [navigate])

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
