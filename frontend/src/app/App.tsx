import { Routes, Route, Navigate } from "react-router-dom"
import LandingPage from "@/features/landing/LandingPage"
import LoginPage from "@/features/auth/LoginPage"
import DashboardPage from "@/features/dashboard/DashboardPage"
import TenantListPage from "@/features/tenants/TenantListPage"
import TenantDetailPage from "@/features/tenants/TenantDetailPage"
import MemberListPage from "@/features/members/MemberListPage"
import MemberDetailPage from "@/features/members/MemberDetailPage"
import ClassListPage from "@/features/classes/ClassListPage"
import ClassDetailPage from "@/features/classes/ClassDetailPage"
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

          {/* Gym-scoped: members (owner + staff + sales baseline) */}
          <Route element={<RequireFeature feature="members" />}>
            <Route path="/members" element={<MemberListPage />} />
            <Route path="/members/:id" element={<MemberDetailPage />} />
          </Route>

          {/* Gym-scoped: classes catalog. Tenant users read; owner mutates. */}
          <Route element={<RequireFeature feature="classes" />}>
            <Route path="/classes" element={<ClassListPage />} />
            <Route path="/classes/:id" element={<ClassDetailPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
