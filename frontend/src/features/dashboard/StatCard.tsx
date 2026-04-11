import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface StatCardProps {
  label: string
  value: string | number
  hint?: string
  icon?: string
}

/** Shared widget — single metric card used by both dashboards. */
export default function StatCard({ label, value, hint, icon }: StatCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {icon && <span className="text-lg">{icon}</span>}
          <CardDescription className="text-sm">{label}</CardDescription>
        </div>
        <CardTitle className="text-3xl font-bold text-gray-900">{value}</CardTitle>
      </CardHeader>
      {hint && (
        <CardContent className="pt-0">
          <p className="text-xs text-gray-400">{hint}</p>
        </CardContent>
      )}
    </Card>
  )
}
