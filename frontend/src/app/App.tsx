import { Routes, Route, Navigate } from "react-router-dom"
import LandingPage from "@/features/landing/LandingPage"
import LoginPage from "@/features/auth/LoginPage"
import DashboardPage from "@/features/dashboard/DashboardPage"
import TenantListPage from "@/features/tenants/TenantListPage"
import UserListPage from "@/features/users/UserListPage"
import ProtectedRoute from "@/components/layout/ProtectedRoute"
import DashboardLayout from "@/components/layout/DashboardLayout"

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/tenants" element={<TenantListPage />} />
          <Route path="/users" element={<UserListPage />} />
          {/* Future:
          <Route path="/members" element={<MemberListPage />} />
          <Route path="/leads" element={<LeadListPage />} />
          */}
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
