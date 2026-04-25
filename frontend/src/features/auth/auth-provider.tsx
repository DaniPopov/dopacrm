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
import type { TenantFeatures } from "./permissions"
import type { User } from "./types"

interface AuthContextValue {
  user: User | null
  /** Per-tenant feature flags from the user's tenant. Empty for
   *  super_admin or while loading. Threaded into ``canAccess`` /
   *  ``accessibleFeatures`` so gated features (coaches, schedule)
   *  hide their sidebar entries when off. */
  tenantFeatures: TenantFeatures
  isAuthenticated: boolean
  isLoading: boolean
  login: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchUser = useCallback(async () => {
    try {
      const u = await getMe()
      setUser(u)
    } catch {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  const loginRefresh = useCallback(async () => {
    // Called after login() succeeds — refetch user from cookie
    await fetchUser()
  }, [fetchUser])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // Server logout failed — continue anyway
    }
    setUser(null)
    navigate("/login")
  }, [navigate])

  return (
    <AuthContext.Provider
      value={{
        user,
        tenantFeatures: user?.tenant_features_enabled ?? {},
        isAuthenticated: !!user,
        isLoading,
        login: loginRefresh,
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
