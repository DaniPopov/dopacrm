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
import PlanListPage from "@/features/plans/PlanListPage"
import PlanDetailPage from "@/features/plans/PlanDetailPage"
import CheckInPage from "@/features/attendance/CheckInPage"
import CoachListPage from "@/features/coaches/CoachListPage"
import CoachDetailPage from "@/features/coaches/CoachDetailPage"
import SchedulePage from "@/features/schedule/SchedulePage"
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

          {/* Gym-scoped: membership plans. Tenant users read; owner mutates. */}
          <Route element={<RequireFeature feature="plans" />}>
            <Route path="/plans" element={<PlanListPage />} />
            <Route path="/plans/:id" element={<PlanDetailPage />} />
          </Route>

          {/* Gym-scoped: attendance / check-in. Staff+ daily operations. */}
          <Route element={<RequireFeature feature="attendance" />}>
            <Route path="/check-in" element={<CheckInPage />} />
          </Route>

          {/* Gym-scoped: coaches + payroll. Owner full CRUD; coach user
              sees their own row + earnings. */}
          <Route element={<RequireFeature feature="coaches" />}>
            <Route path="/coaches" element={<CoachListPage />} />
            <Route path="/coaches/:id" element={<CoachDetailPage />} />
          </Route>

          {/* Gym-scoped: weekly schedule. Owner edits; coach sees own
              sessions read-only. Gated by tenant feature flag. */}
          <Route element={<RequireFeature feature="schedule" />}>
            <Route path="/schedule" element={<SchedulePage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
