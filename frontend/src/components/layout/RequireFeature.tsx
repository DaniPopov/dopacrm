import { Navigate, Outlet } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"
import { canAccess, type Feature } from "@/features/auth/permissions"

/**
 * Route-level permission guard.
 *
 * Wraps a <Route> (or group of routes) and only renders them if the
 * current user has access to the given feature. Used in tandem with
 * the sidebar: sidebar hides links, this guard blocks direct URL access.
 *
 * Usage:
 *   <Route element={<RequireFeature feature="tenants" />}>
 *     <Route path="/tenants" element={<TenantListPage />} />
 *   </Route>
 *
 * If the user lacks access, they get redirected to /dashboard. We don't
 * show a 403 page because the sidebar never offered the link in the first
 * place — hitting this guard means someone typed a URL directly.
 */
export default function RequireFeature({ feature }: { feature: Feature }) {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  if (!canAccess(user, feature)) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
