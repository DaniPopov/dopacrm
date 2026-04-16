import { useEffect, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import { useDevice } from "@/hooks/useDevice"
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed"
import Sidebar from "./Sidebar"

const dopaIcon = "/dopa-icon.png"

/**
 * Dashboard shell.
 *
 * - Desktop / tablet: persistent sidebar on the right (RTL). Can be
 *   collapsed to an icon-only 64px rail via the chevron toggle in the
 *   sidebar header. State persists via localStorage (see
 *   `useSidebarCollapsed`) so the preference sticks across reloads.
 * - Mobile: top bar with a hamburger that toggles a drawer. ESC and
 *   backdrop click also close.
 *
 * An app-level footer ("Developed by Dopamineo") sits at the bottom
 * of the main column on all layouts.
 */
export default function DashboardLayout() {
  const { isMobile } = useDevice()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [collapsed, toggleCollapsed] = useSidebarCollapsed()
  const location = useLocation()

  // Close drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // ESC closes the mobile drawer.
  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [drawerOpen])

  return (
    <div
      dir="rtl"
      className="flex min-h-screen bg-gray-50"
      style={{ fontFamily: "'Rubik', sans-serif" }}
    >
      {isMobile ? (
        <MobileLayout
          drawerOpen={drawerOpen}
          onToggleDrawer={() => setDrawerOpen((v) => !v)}
          onCloseDrawer={() => setDrawerOpen(false)}
        />
      ) : (
        <DesktopLayout collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
      )}
    </div>
  )
}

/* ── Desktop / tablet ─────────────────────────────────────────── */

function DesktopLayout({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean
  onToggleCollapsed: () => void
}) {
  // Match the sidebar width: w-56 (224px) expanded, w-16 (64px) collapsed
  const sidebarWidthClass = collapsed ? "w-16" : "w-56"
  const mainOffsetClass = collapsed ? "mr-16" : "mr-56"

  return (
    <>
      <div
        className={`fixed right-0 top-0 z-40 h-full transition-all duration-200 ${sidebarWidthClass}`}
      >
        <Sidebar collapsed={collapsed} onToggleCollapse={onToggleCollapsed} />
      </div>
      <div
        className={`flex flex-1 flex-col transition-all duration-200 ${mainOffsetClass}`}
      >
        <main className="mx-auto w-full max-w-6xl flex-1 px-8 py-8">
          <Outlet />
        </main>
        <AppFooter />
      </div>
    </>
  )
}

/* ── Mobile ───────────────────────────────────────────────────── */

function MobileLayout({
  drawerOpen,
  onToggleDrawer,
  onCloseDrawer,
}: {
  drawerOpen: boolean
  onToggleDrawer: () => void
  onCloseDrawer: () => void
}) {
  return (
    <div className="flex min-h-screen w-full flex-col">
      {/* Top bar — hamburger on the right (drawer edge), logo on the left */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 shadow-sm">
        <button
          onClick={onToggleDrawer}
          aria-label={drawerOpen ? "סגירת תפריט" : "פתיחת תפריט"}
          aria-expanded={drawerOpen}
          className="rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100"
        >
          {drawerOpen ? <CloseIcon /> : <HamburgerIcon />}
        </button>
        <div className="flex items-center gap-2">
          <img src={dopaIcon} alt="" className="h-6 w-6" />
          <span className="text-base font-bold text-gray-900">DopaCRM</span>
        </div>
      </header>

      {/* Drawer — pinned flush to the right edge */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-50"
          role="dialog"
          aria-label="תפריט ניווט"
          aria-modal="true"
        >
          <button
            type="button"
            aria-label="סגירת תפריט"
            onClick={onCloseDrawer}
            className="absolute inset-0 cursor-default bg-black/40"
          />
          <div className="absolute right-0 top-0 h-full w-64 animate-[slideInRight_0.2s_ease-out] bg-white shadow-2xl">
            <Sidebar onNavigate={onCloseDrawer} />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 px-4 py-6">
        <Outlet />
      </main>

      <AppFooter />
    </div>
  )
}

/* ── App footer ───────────────────────────────────────────────── */

/**
 * App-level footer pinned to the bottom of the main column.
 * Renders the same on desktop and mobile — small dopa logo inline
 * next to the "Dopamineo" wordmark.
 */
function AppFooter() {
  return (
    <footer className="border-t border-gray-100 bg-white px-4 py-3 text-xs text-gray-400">
      <div className="flex items-center justify-center gap-1.5">
        <img src={dopaIcon} alt="" className="h-4 w-4" />
        <span className="font-semibold text-gray-500">Dopamineo</span>
        <span>Developed by</span>
      </div>
    </footer>
  )
}

/* ── Icons ────────────────────────────────────────────────────── */

function HamburgerIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
