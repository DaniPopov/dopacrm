import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div dir="rtl" className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <h1 className="text-xl font-bold">DopaCRM</h1>
          <Button variant="outline" onClick={() => navigate("/login")}>
            כניסה לפורטל
          </Button>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-7xl px-6 py-24 text-center">
        <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
          מערכת ניהול חדר כושר
        </h2>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          נהלו מנויים, עקבו אחרי הכנסות, טפלו בלידים — הכל ממקום אחד.
          DopaCRM נבנה במיוחד לחדרי כושר וסטודיואים.
        </p>
        <div className="mt-10">
          <Button size="lg" onClick={() => navigate("/login")}>
            התחילו עכשיו
          </Button>
        </div>
      </section>

      {/* Features */}
      <section className="border-t bg-muted/50 py-20">
        <div className="mx-auto max-w-7xl px-6">
          <h3 className="mb-12 text-center text-2xl font-semibold">
            מה תקבלו?
          </h3>
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            <FeatureCard
              title="ניהול מנויים"
              description="פרופילים, סטטוס, תוכניות, הקפאות — הכל מסודר במקום אחד."
            />
            <FeatureCard
              title="מעקב הכנסות"
              description="הכנסה לפי מנוי, לפי תוכנית, לפי חודש. תמיד יודעים מה המצב."
            />
            <FeatureCard
              title="ניהול לידים"
              description="מעקב אחרי לידים מהרגע שנכנסים ועד שהופכים למנויים."
            />
            <FeatureCard
              title="דשבורד חכם"
              description="מספרים חשובים במבט אחד — MRR, נטישה, מנויים חדשים."
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8 text-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} DopaCRM by Dopamineo. כל הזכויות שמורות.</p>
      </footer>
    </div>
  )
}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border bg-card p-6 text-right">
      <h4 className="mb-2 font-semibold">{title}</h4>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
