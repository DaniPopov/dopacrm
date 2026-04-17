import type { ReactNode } from "react"

/**
 * The rounded-xl card wrapper used everywhere for content sections.
 * Replaces the bare `<div className="rounded-xl border...">` copy-paste
 * in dashboards, detail pages, forms.
 *
 * Pass `title` to render an H2 inside the card. Omit it if you want a
 * header-less card (e.g., a form wrapper with its own heading).
 */
export function SectionCard({
  title,
  action,
  children,
  className,
}: {
  title?: string
  /** Optional right-aligned control next to the title (e.g., a filter toggle). */
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-xl border border-gray-200 bg-white p-6 shadow-sm ${
        className ?? ""
      }`}
    >
      {title && (
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
