import type { ReactNode } from "react"

/**
 * Shared page header for every list / detail page in the CRM.
 *
 * Gives a consistent "title + subtitle + right-side action" layout. On
 * mobile the action stretches to full width; on desktop it sits next to
 * the title. Works for:
 *   - List pages: title + "+ Add" button
 *   - Detail pages: title + "חזרה לרשימה" back link (pass a link as action)
 *
 * Omit `action` if there's nothing on the right.
 */
export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
