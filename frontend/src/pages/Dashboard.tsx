import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface User {
  id: string
  email: string
  full_name: string
  role: string
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      navigate("/login")
      return
    }

    fetch("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Unauthorized")
        return res.json()
      })
      .then((data) => setUser(data))
      .catch(() => {
        localStorage.removeItem("token")
        navigate("/login")
      })
      .finally(() => setLoading(false))
  }, [navigate])

  function handleLogout() {
    localStorage.removeItem("token")
    navigate("/login")
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <h1 className="text-xl font-semibold">DopaCRM</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              {user?.full_name}
            </span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <h2 className="mb-6 text-2xl font-semibold">Dashboard</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardDescription>Total Members</CardDescription>
              <CardTitle className="text-3xl">--</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">Coming soon</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Active Plans</CardDescription>
              <CardTitle className="text-3xl">--</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">Coming soon</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Monthly Revenue</CardDescription>
              <CardTitle className="text-3xl">--</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">Coming soon</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Open Leads</CardDescription>
              <CardTitle className="text-3xl">--</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">Coming soon</p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
