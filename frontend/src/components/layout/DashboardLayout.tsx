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
 * - Mobile: top bar with hamburger that TOGGLES the drawer (opens if
 *   closed, closes if open). Drawer auto-closes on route change so it
 *   doesn't linger after tapping a link. ESC key also closes it.
 */
export default function DashboardLayout() {
  const { isMobile } = useDevice()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()

  // Close drawer whenever the route changes (user tapped a link).
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // ESC closes the drawer.
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

      {/* Drawer — absolute positioning pins it flush to the right edge,
          regardless of flex/RTL quirks. */}
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
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
