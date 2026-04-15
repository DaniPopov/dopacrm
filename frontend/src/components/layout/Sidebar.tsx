import { NavLink } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"
import { canAccess, type Feature } from "@/features/auth/permissions"
import type { User } from "@/features/auth/types"

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

  // Platform admin — user management lives inside /tenants/:id
  { to: "/tenants", label: "חדרי כושר", icon: "🏢", feature: "tenants" },

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

      {/* User banner + logout */}
      <div className="border-t border-gray-100 p-3">
        <UserBanner user={user} />
        <button
          onClick={logout}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-red-50 hover:text-red-600"
        >
          <LogoutIcon />
          התנתקות
        </button>
      </div>
    </aside>
  )
}

/* ── User banner — avatar circle + name + email ──────────────── */

function UserBanner({ user }: { user: User | null }) {
  if (!user) return null

  const initials = getInitials(user)
  const displayName = getDisplayName(user)

  return (
    <div className="flex items-center gap-3 rounded-xl bg-gray-50 px-3 py-2.5">
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-700 text-sm font-semibold text-white">
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-gray-900">{displayName}</div>
        <div className="truncate text-xs text-gray-500">{user.email}</div>
      </div>
    </div>
  )
}

/**
 * Build initials. Prefers first_name + last_name; falls back to parsing
 * the email local-part (splitting on dot/underscore/hyphen) when the
 * name fields aren't set.
 */
function getInitials(user: User): string {
  if (user.first_name || user.last_name) {
    const a = user.first_name?.charAt(0) ?? ""
    const b = user.last_name?.charAt(0) ?? ""
    return (a + b).toUpperCase() || "?"
  }
  const local = user.email.split("@")[0] ?? ""
  const parts = local.split(/[._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
  return (local.charAt(0) || "?").toUpperCase()
}

function getDisplayName(user: User): string {
  if (user.first_name || user.last_name) {
    return [user.first_name, user.last_name].filter(Boolean).join(" ")
  }
  return user.email.split("@")[0] ?? user.email
}

/* ── Nav link ─────────────────────────────────────────────────── */

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

function LogoutIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}
