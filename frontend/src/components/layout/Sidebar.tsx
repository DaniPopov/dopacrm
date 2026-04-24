import { NavLink } from "react-router-dom"
import { useAuth } from "@/features/auth/auth-provider"
import { canAccess, type Feature } from "@/features/auth/permissions"
import type { User } from "@/features/auth/types"
import { useTenant } from "@/features/tenants/hooks"

const dopaIcon = "/dopa-icon.png"

/**
 * Role-based sidebar navigation.
 *
 * Branding:
 * - super_admin (no tenant) → shows the DopaCRM logo + name (platform view)
 * - tenant user (owner/staff/sales) → shows their gym's logo + name,
 *   falling back to DopaCRM defaults if the gym hasn't uploaded a logo
 *   or until `useTenant` resolves.
 *
 * Collapse (desktop only):
 * - When `collapsed=true`, the sidebar shrinks to icon-only (64px wide).
 *   Labels, the brand name, the user banner text, and the logout label
 *   all hide — icons remain for a compact rail.
 * - The toggle button stays visible in both states.
 *
 * Mobile: the drawer version doesn't collapse (it's either open or
 * not). `DashboardLayout` controls that separately.
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

  // Gym-scoped
  { to: "/members", label: "מנויים", icon: "👥", feature: "members" },
  { to: "/check-in", label: "כניסות", icon: "🚪", feature: "attendance" },
  { to: "/classes", label: "שיעורים", icon: "🏃", feature: "classes" },
  { to: "/plans", label: "מסלולים", icon: "📋", feature: "plans" },
  { to: "/coaches", label: "מאמנים", icon: "🥋", feature: "coaches" },

  // Future (placeholders — routes land with feature work)
  // { to: "/leads", label: "לידים", icon: "🎯", feature: "leads" },
  // { to: "/payments", label: "תשלומים", icon: "💰", feature: "payments" },
  // { to: "/settings", label: "הגדרות", icon: "⚙️", feature: "settings" },
]

interface SidebarProps {
  /** Called when a link is tapped — closes the drawer on mobile. */
  onNavigate?: () => void
  /** Desktop collapsed state. Ignored in the mobile drawer. */
  collapsed?: boolean
  /** Toggle collapsed ↔ expanded. Ignored when `collapsed` is undefined. */
  onToggleCollapse?: () => void
}

export default function Sidebar({
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: SidebarProps = {}) {
  const { user, logout } = useAuth()
  const visibleItems = NAV_ITEMS.filter((item) => canAccess(user, item.feature))

  // Tenant branding: fetch only when user is tenant-scoped
  const tenantId = user?.tenant_id ?? ""
  const { data: tenant } = useTenant(tenantId)

  const brandLogo = tenant?.logo_presigned_url ?? dopaIcon
  const brandName = tenant?.name ?? "DopaCRM"

  return (
    <aside
      className={`flex h-full flex-col border-l border-gray-200 bg-white transition-all duration-200 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Logo + optional collapse toggle */}
      <div
        className={`flex items-center gap-2.5 border-b border-gray-100 py-4 ${
          collapsed ? "px-2 justify-center" : "px-5"
        }`}
      >
        <img
          src={brandLogo}
          alt=""
          className="h-7 w-7 flex-shrink-0 rounded object-cover"
        />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 truncate text-base font-bold text-gray-900">
              {brandName}
            </span>
            {onToggleCollapse && (
              <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapse} />
            )}
          </>
        )}
      </div>

      {/* When collapsed, the toggle moves below the logo for visibility */}
      {collapsed && onToggleCollapse && (
        <div className="flex justify-center border-b border-gray-100 py-1">
          <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapse} />
        </div>
      )}

      {/* Nav links */}
      <nav className={`flex-1 space-y-1 py-4 ${collapsed ? "px-2" : "px-3"}`}>
        {visibleItems.map((item) => (
          <SidebarLink
            key={item.to}
            to={item.to}
            icon={item.icon}
            label={item.label}
            collapsed={collapsed}
            onClick={onNavigate}
          />
        ))}
      </nav>

      {/* User banner + logout */}
      <div className={`border-t border-gray-100 ${collapsed ? "p-2" : "p-3"}`}>
        {!collapsed && <UserBanner user={user} />}

        <button
          onClick={logout}
          className={`mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-red-50 hover:text-red-600 ${
            collapsed ? "justify-center" : "justify-center"
          }`}
          aria-label="התנתקות"
          title={collapsed ? "התנתקות" : undefined}
        >
          <LogoutIcon />
          {!collapsed && <span>התנתקות</span>}
        </button>
      </div>
    </aside>
  )
}

/* ── Collapse toggle button ───────────────────────────────────── */

/**
 * Chevron button that flips between expanded/collapsed.
 * Arrow points toward where the sidebar will MOVE when clicked —
 * in RTL, a right-pointing chevron (→) expands (opens the sidebar
 * to the left), left-pointing (←) collapses.
 */
function CollapseToggle({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={collapsed ? "פתח סרגל" : "סגור סרגל"}
      title={collapsed ? "פתח סרגל" : "סגור סרגל"}
      className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        // flip horizontally when collapsed so the chevron points "outward"
        style={{ transform: collapsed ? "scaleX(-1)" : undefined }}
      >
        <polyline points="15 18 9 12 15 6" />
      </svg>
    </button>
  )
}

/* ── User banner ──────────────────────────────────────────────── */

/**
 * Avatar circle + name + email inside the collapsed-footer zone.
 * Hidden entirely when the sidebar is collapsed.
 */
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
 * Two-letter avatar initials. Prefers first_name + last_name, falls
 * back to parsing the email local-part on dot/hyphen/underscore.
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
  collapsed,
  onClick,
}: {
  to: string
  icon: string
  label: string
  collapsed: boolean
  onClick?: () => void
}) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg py-2 text-sm font-medium transition-colors ${
          collapsed ? "justify-center px-2" : "px-3"
        } ${
          isActive
            ? "bg-blue-50 text-blue-700"
            : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
        }`
      }
    >
      <span className="text-base">{icon}</span>
      {!collapsed && <span>{label}</span>}
    </NavLink>
  )
}

/** Log-out icon — used next to the התנתקות label, or alone when collapsed. */
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
