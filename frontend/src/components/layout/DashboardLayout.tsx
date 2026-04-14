import { useEffect, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import { useDevice } from "@/hooks/useDevice"
import Sidebar from "./Sidebar"

const dopaIcon = "/dopa-icon.png"

/**
 * Dashboard shell.
 *
 * - Desktop / tablet: persistent fixed sidebar on the right (RTL layout),
 *   main content gets a matching margin.
 * - Mobile: top bar with hamburger. Sidebar opens in an overlay drawer.
 *   Drawer auto-closes on route change so it doesn't linger after
 *   tapping a link.
 */
export default function DashboardLayout() {
  const { isMobile } = useDevice()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // Close drawer whenever the route changes (user tapped a link).
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  return (
    <div
      dir="rtl"
      className="flex min-h-screen bg-gray-50"
      style={{ fontFamily: "'Rubik', sans-serif" }}
    >
      {isMobile ? (
        <MobileLayout
          drawerOpen={drawerOpen}
          onOpenDrawer={() => setDrawerOpen(true)}
          onCloseDrawer={() => setDrawerOpen(false)}
        />
      ) : (
        <DesktopLayout />
      )}
    </div>
  )
}

/* ── Desktop / tablet ─────────────────────────────────────────── */

function DesktopLayout() {
  return (
    <>
      <div className="fixed right-0 top-0 z-40 h-full w-56">
        <Sidebar />
      </div>
      <div className="mr-56 flex-1">
        <main className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </main>
      </div>
    </>
  )
}

/* ── Mobile ───────────────────────────────────────────────────── */

function MobileLayout({
  drawerOpen,
  onOpenDrawer,
  onCloseDrawer,
}: {
  drawerOpen: boolean
  onOpenDrawer: () => void
  onCloseDrawer: () => void
}) {
  return (
    <div className="flex min-h-screen w-full flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <img src={dopaIcon} alt="" className="h-6 w-6" />
          <span className="text-base font-bold text-gray-900">DopaCRM</span>
        </div>
        <button
          onClick={onOpenDrawer}
          aria-label="פתיחת תפריט"
          className="rounded-lg p-2 text-gray-600 transition-colors hover:bg-gray-100"
        >
          <HamburgerIcon />
        </button>
      </header>

      {/* Drawer overlay */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-50 flex"
          role="dialog"
          aria-label="תפריט ניווט"
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={onCloseDrawer}
            aria-hidden="true"
          />
          <div className="relative ml-auto h-full w-64 animate-[slideInRight_0.2s_ease-out] bg-white shadow-2xl">
            <button
              onClick={onCloseDrawer}
              aria-label="סגירת תפריט"
              className="absolute left-3 top-3 z-10 rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
            >
              <CloseIcon />
            </button>
            <Sidebar onNavigate={onCloseDrawer} />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

/* ── Icons (inline SVG — no new dep) ──────────────────────────── */

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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
