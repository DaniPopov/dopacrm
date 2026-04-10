import { NavLink, Outlet } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"

const dopaIcon = "/dopa-icon.png"

export default function DashboardLayout() {
  const { user, logout } = useAuth()
  const isSuperAdmin = user?.role === "super_admin"

  return (
    <div dir="rtl" className="flex min-h-screen bg-gray-50" style={{ fontFamily: "'Rubik', sans-serif" }}>
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside className="fixed right-0 top-0 z-40 flex h-full w-56 flex-col border-l border-gray-200 bg-white">
        {/* Logo */}
        <div className="flex items-center gap-2.5 border-b border-gray-100 px-5 py-4">
          <img src={dopaIcon} alt="" className="h-7 w-7" />
          <span className="text-base font-bold text-gray-900">DopaCRM</span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          <SidebarLink to="/dashboard" icon="📊" label="דשבורד" />
          {isSuperAdmin && (
            <SidebarLink to="/tenants" icon="🏢" label="חדרי כושר" />
          )}
          {isSuperAdmin && (
            <SidebarLink to="/users" icon="👤" label="משתמשים" />
          )}
          {/* Future — visible to all roles:
          <SidebarLink to="/members" icon="👥" label="מנויים" />
          <SidebarLink to="/plans" icon="📋" label="תוכניות" />
          <SidebarLink to="/leads" icon="🎯" label="לידים" />
          <SidebarLink to="/payments" icon="💰" label="תשלומים" />
          */}
        </nav>

        {/* User + logout */}
        <div className="border-t border-gray-100 px-4 py-3">
          <div className="mb-2 truncate text-xs text-gray-500">{user?.email}</div>
          <button
            onClick={logout}
            className="w-full rounded-lg px-3 py-1.5 text-right text-sm text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
          >
            התנתקות
          </button>
        </div>
      </aside>

      {/* ── Main content ────────────────────────────────────────── */}
      <div className="mr-56 flex-1">
        <main className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function SidebarLink({ to, icon, label }: { to: string; icon: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          isActive
            ? "bg-blue-50 text-blue-700"
            : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
        }`
      }
    >
      <span className="text-base">{icon}</span>
      {label}
    </NavLink>
  )
}
