import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"

/**
 * Dashboard shell — sidebar + routed main content.
 * Sidebar handles its own role-based nav (see Sidebar.tsx).
 */
export default function DashboardLayout() {
  return (
    <div dir="rtl" className="flex min-h-screen bg-gray-50" style={{ fontFamily: "'Rubik', sans-serif" }}>
      <Sidebar />
      <div className="mr-56 flex-1">
        <main className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
