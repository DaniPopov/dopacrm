import { useNavigate } from "react-router-dom"

const dopaIcon = "/dopa-icon.png"
const crmImage = "/dopamineocrm-image.png"
const gymImage = "/dopamineogym-image.png"

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div dir="rtl" className="min-h-screen bg-white" style={{ fontFamily: "'Rubik', sans-serif" }}>
      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav className="fixed top-0 right-0 left-0 z-50 border-b border-white/10 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex items-center gap-2 sm:gap-3">
            <img src={dopaIcon} alt="DopaCRM" className="h-7 w-7 sm:h-8 sm:w-8" />
            <span className="text-base font-bold text-gray-900 sm:text-lg">DopaCRM</span>
          </div>
          <button
            onClick={() => navigate("/login")}
            className="rounded-full border border-blue-600 px-4 py-1.5 text-sm font-medium text-blue-600 transition-all hover:bg-blue-600 hover:text-white sm:px-5 sm:py-2"
          >
            כניסה לפורטל
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-24">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-bl from-blue-50 via-white to-cyan-50" />
        <div
          className="absolute top-20 left-1/4 h-[500px] w-[500px] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, #2563EB 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 right-1/4 h-[400px] w-[400px] rounded-full opacity-15 blur-3xl"
          style={{ background: "radial-gradient(circle, #06B6D4 0%, transparent 70%)" }}
        />

        <div className="relative mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-20 lg:py-28">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-12">
            {/* Text */}
            <div className="animate-[fadeInRight_0.8s_ease-out]">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 sm:mb-6 sm:px-4 sm:text-sm">
                <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                המערכת המובילה לניהול חדרי כושר
              </div>
              <h1 className="text-3xl font-extrabold leading-tight text-gray-900 sm:text-5xl lg:text-6xl">
                נהלו את חדר הכושר
                <br />
                <span className="bg-gradient-to-l from-blue-600 to-cyan-500 bg-clip-text text-transparent">
                  כמו מקצוענים
                </span>
              </h1>
              <p className="mt-4 max-w-lg text-base leading-relaxed text-gray-600 sm:mt-6 sm:text-lg">
                מנויים, הכנסות, לידים, תוכניות — הכל במקום אחד.
                DopaCRM נבנה מהיסוד לחדרי כושר וסטודיואים בישראל.
              </p>
              <div className="mt-6 flex flex-wrap gap-3 sm:mt-10 sm:gap-4">
                <button
                  onClick={() => navigate("/login")}
                  className="w-full rounded-xl bg-gradient-to-l from-blue-600 to-blue-700 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-500/25 transition-all hover:shadow-xl hover:shadow-blue-500/30 hover:-translate-y-0.5 sm:w-auto sm:px-8 sm:py-3.5 sm:text-base"
                >
                  התחילו בחינם
                </button>
                <button
                  className="w-full rounded-xl border-2 border-gray-200 bg-white px-6 py-3 text-sm font-semibold text-gray-700 transition-all hover:border-blue-300 hover:text-blue-600 sm:w-auto sm:px-8 sm:py-3.5 sm:text-base"
                >
                  צפו בהדגמה
                </button>
              </div>
            </div>

            {/* Hero image */}
            <div className="relative flex justify-center animate-[fadeInLeft_0.8s_ease-out]">
              <div className="relative">
                <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 blur-2xl" />
                <img
                  src={crmImage}
                  alt="DopamineoCRM"
                  className="relative w-full rounded-2xl shadow-2xl shadow-blue-900/10"
                  style={{ maxHeight: "460px" }}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats bar ────────────────────────────────────────────────── */}
      <section className="relative border-y border-gray-100 bg-gray-50/50">
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-8 px-6 py-12 sm:grid-cols-4">
          {[
            { number: "500+", label: "חדרי כושר" },
            { number: "50K+", label: "מנויים מנוהלים" },
            { number: "99.9%", label: "זמינות" },
            { number: "24/7", label: "תמיכה" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-3xl font-extrabold text-blue-600">{stat.number}</div>
              <div className="mt-1 text-sm text-gray-500">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────── */}
      <section className="py-24">
        <div className="mx-auto max-w-7xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-gray-900 sm:text-4xl">
              הכל מה שחדר כושר צריך
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-gray-500">
              מערכת אחת שמחליפה את כל הגיליונות, האקסלים והמערכות המפוזרות
            </p>
          </div>

          <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <FeatureCard
              icon="👥"
              title="ניהול מנויים"
              description="פרופילים מלאים, סטטוס מנוי, תוכניות, הקפאות וחידושים אוטומטיים."
              color="blue"
            />
            <FeatureCard
              icon="💰"
              title="מעקב הכנסות"
              description="הכנסה לפי מנוי, תוכנית וחודש. דוחות MRR, נטישה וצמיחה."
              color="emerald"
            />
            <FeatureCard
              icon="🎯"
              title="ניהול לידים"
              description="מעקב מהרגע שנכנסים ועד שהופכים למנויים. צינור מכירות חכם."
              color="purple"
            />
            <FeatureCard
              icon="📊"
              title="דשבורד מותאם אישית"
              description="בחרו אילו גרפים לראות, באילו תאריכים. כל בעל עסק רואה מה שחשוב לו."
              color="amber"
            />
            <FeatureCard
              icon="⚡"
              title="מהיר ופשוט"
              description="ממשק נקי שעובד. בלי עקומת למידה. התחילו לעבוד באותו יום."
              color="rose"
            />
            <FeatureCard
              icon="🔒"
              title="מאובטח"
              description="הצפנה, הרשאות לפי תפקיד, ומערכת multi-tenant מבודדת לכל עסק."
              color="cyan"
            />
          </div>
        </div>
      </section>

      {/* ── CTA with gym image ───────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-l from-gray-900 to-blue-900 py-24">
        <div
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="relative mx-auto max-w-7xl px-6">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div className="flex justify-center lg:order-2">
              <img
                src={gymImage}
                alt="DopamineoGym"
                className="rounded-2xl shadow-2xl"
                style={{ maxHeight: "380px" }}
              />
            </div>
            <div className="lg:order-1">
              <h2 className="text-3xl font-bold text-white sm:text-4xl">
                מוכנים לשדרג את חדר הכושר?
              </h2>
              <p className="mt-4 text-lg text-blue-100/80">
                הצטרפו למאות חדרי כושר שכבר עברו ל-DopaCRM.
                התחילו בחינם, שדרגו כשתרצו.
              </p>
              <button
                onClick={() => navigate("/login")}
                className="mt-8 rounded-xl bg-white px-8 py-3.5 text-base font-semibold text-blue-900 shadow-lg transition-all hover:shadow-xl hover:-translate-y-0.5"
              >
                התחילו עכשיו — בחינם
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t bg-gray-50 py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
            <div className="flex items-center gap-2">
              <img src={dopaIcon} alt="" className="h-6 w-6" />
              <span className="font-semibold text-gray-700">DopaCRM</span>
              <span className="text-sm text-gray-400">by Dopamineo</span>
            </div>
            <p className="text-sm text-gray-400">
              &copy; {new Date().getFullYear()} כל הזכויות שמורות.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

const colorMap = {
  blue: "from-blue-500/10 to-blue-500/5 border-blue-100",
  emerald: "from-emerald-500/10 to-emerald-500/5 border-emerald-100",
  purple: "from-purple-500/10 to-purple-500/5 border-purple-100",
  amber: "from-amber-500/10 to-amber-500/5 border-amber-100",
  rose: "from-rose-500/10 to-rose-500/5 border-rose-100",
  cyan: "from-cyan-500/10 to-cyan-500/5 border-cyan-100",
}

function FeatureCard({
  icon,
  title,
  description,
  color,
}: {
  icon: string
  title: string
  description: string
  color: keyof typeof colorMap
}) {
  return (
    <div
      className={`rounded-2xl border bg-gradient-to-b p-7 transition-all hover:-translate-y-1 hover:shadow-lg ${colorMap[color]}`}
    >
      <div className="mb-4 text-3xl">{icon}</div>
      <h4 className="mb-2 text-lg font-bold text-gray-900">{title}</h4>
      <p className="text-sm leading-relaxed text-gray-500">{description}</p>
    </div>
  )
}
