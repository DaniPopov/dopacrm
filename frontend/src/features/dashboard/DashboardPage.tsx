import { useAuth } from "@/features/auth/auth-provider"
import AdminDashboard from "./AdminDashboard"
import GymDashboard from "./GymDashboard"

/**
 * One route, role-based content:
 * - super_admin → AdminDashboard (platform metrics)
 * - owner / staff / sales → GymDashboard (tenant metrics)
 */
export default function DashboardPage() {
  const { user } = useAuth()
  if (user?.role === "super_admin") return <AdminDashboard />
  return <GymDashboard />
}
