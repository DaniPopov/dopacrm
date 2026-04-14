import { NavLink } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"
import { canAccess, type Feature } from "@/features/auth/permissions"

const dopaIcon = "/dopa-icon.png"

/**
 * Role-based sidebar navigation.
 *
 * Each nav item is tied to a Feature. Visibility is decided by
 * permissions.canAccess — NOT by role arrays. This way, when the
 * backend starts returning owner-configured tenant overrides,
 * the sidebar adapts automatically.
 *
 * Layout:
 * - Desktop / tablet: persistent fixed sidebar (rendered by DashboardLayout)
 * - Mobile: rendered inside an overlay drawer (also by DashboardLayout)
 *
 * `onNavigate` lets the parent close the mobile drawer after a link click.
 */
interface NavItem {
  to: string
  label: string
  icon: string
  feature: Feature
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "דשבורד", icon: "📊", feature: "dashboard" },

  // Platform admin
  { to: "/tenants", label: "חדרי כושר", icon: "🏢", feature: "tenants" },
  { to: "/users", label: "משתמשים", icon: "👤", feature: "platform_users" },

  // Gym-scoped (placeholders — routes land with feature work)
  // { to: "/members", label: "מנויים", icon: "👥", feature: "members" },
  // { to: "/plans", label: "תוכניות", icon: "📋", feature: "plans" },
  // { to: "/leads", label: "לידים", icon: "🎯", feature: "leads" },
  // { to: "/payments", label: "תשלומים", icon: "💰", feature: "payments" },
  // { to: "/settings", label: "הגדרות", icon: "⚙️", feature: "settings" },
]

export default function Sidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const { user, logout } = useAuth()
  const visibleItems = NAV_ITEMS.filter((item) => canAccess(user, item.feature))

  return (
    <aside className="flex h-full w-56 flex-col border-l border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex items-center gap-2.5 border-b border-gray-100 px-5 py-4">
        <img src={dopaIcon} alt="" className="h-7 w-7" />
        <span className="text-base font-bold text-gray-900">DopaCRM</span>
      </div>

      {/* Nav links */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {visibleItems.map((item) => (
          <SidebarLink
            key={item.to}
            to={item.to}
            icon={item.icon}
            label={item.label}
            onClick={onNavigate}
          />
        ))}
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
  )
}

function SidebarLink({
  to,
  icon,
  label,
  onClick,
}: {
  to: string
  icon: string
  label: string
  onClick?: () => void
}) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
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
