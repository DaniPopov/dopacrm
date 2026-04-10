import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import dopaIcon from "@/app/assets/dopa-icon.png"
import gymImage from "@/app/assets/dopamineogym-image.png"
import { login } from "./api"

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const data = await login({ email, password })
      localStorage.setItem("token", data.access_token)
      navigate("/dashboard")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect to server")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      dir="rtl"
      className="flex min-h-screen"
      style={{ fontFamily: "'Rubik', sans-serif" }}
    >
      {/* ── Left panel: branding ─────────────────────────────────── */}
      <div className="hidden relative overflow-hidden lg:flex lg:w-1/2 items-center justify-center bg-gradient-to-bl from-blue-600 to-blue-800">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
        <div
          className="absolute top-1/4 right-1/4 h-[400px] w-[400px] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, #06B6D4 0%, transparent 70%)" }}
        />

        <div className="relative z-10 flex flex-col items-center px-12 text-center">
          <img
            src={gymImage}
            alt="DopamineoGym"
            className="mb-10 rounded-2xl shadow-2xl shadow-black/20"
            style={{ maxHeight: "340px" }}
          />
          <h2 className="text-3xl font-bold text-white">
            DopaCRM
          </h2>
          <p className="mt-3 max-w-sm text-base text-blue-100/70">
            מערכת ניהול חדר כושר מתקדמת. מנויים, הכנסות, לידים — הכל במקום אחד.
          </p>
        </div>
      </div>

      {/* ── Right panel: login form ──────────────────────────────── */}
      <div className="flex w-full flex-col items-center justify-center bg-gray-50 px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          {/* Logo + title */}
          <div className="mb-10 flex flex-col items-center">
            <img src={dopaIcon} alt="DopaCRM" className="mb-4 h-12 w-12" />
            <h1 className="text-2xl font-bold text-gray-900">כניסה לפורטל</h1>
            <p className="mt-1 text-sm text-gray-500">
              הזינו את פרטי ההתחברות שלכם
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-gray-700">
                אימייל
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@gym.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-900 outline-none transition-all placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-gray-700">
                סיסמה
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 pl-11 text-sm text-gray-900 outline-none transition-all placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-600"
                  aria-label={showPassword ? "הסתר סיסמה" : "הצג סיסמה"}
                >
                  {showPassword ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-gradient-to-l from-blue-600 to-blue-700 py-3 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition-all hover:shadow-lg hover:shadow-blue-500/25 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? "מתחבר..." : "התחברות"}
            </button>
          </form>

          {/* Back to landing */}
          <div className="mt-8 text-center">
            <button
              onClick={() => navigate("/")}
              className="text-sm text-gray-400 transition-colors hover:text-blue-600"
            >
              חזרה לעמוד הראשי
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
