import { Routes, Route, Navigate } from "react-router-dom"
import LandingPage from "@/features/landing/LandingPage"
import LoginPage from "@/features/auth/LoginPage"
import DashboardPage from "@/features/dashboard/DashboardPage"
import TenantListPage from "@/features/tenants/TenantListPage"
import TenantDetailPage from "@/features/tenants/TenantDetailPage"
import ProtectedRoute from "@/components/layout/ProtectedRoute"
import RequireFeature from "@/components/layout/RequireFeature"
import DashboardLayout from "@/components/layout/DashboardLayout"

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />

          {/* Platform admin only — URL-typing doesn't bypass the sidebar.
              User management is nested under /tenants/:id (no standalone /users page). */}
          <Route element={<RequireFeature feature="tenants" />}>
            <Route path="/tenants" element={<TenantListPage />} />
            <Route path="/tenants/:id" element={<TenantDetailPage />} />
          </Route>

          {/* Future gym-scoped routes wrap with RequireFeature too:
          <Route element={<RequireFeature feature="members" />}>
            <Route path="/members" element={<MemberListPage />} />
          </Route>
          */}
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
