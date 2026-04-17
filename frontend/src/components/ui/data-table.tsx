import type { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useDevice } from "@/hooks/useDevice"

/**
 * Shared data-table primitive.
 *
 * One component for every list page in the CRM (members / classes / plans /
 * tenants). Gives us:
 *
 * - **Consistent look** across the app — rounded container, row dividers,
 *   hover state, RTL-correct columns.
 * - **Responsive out of the box** — renders as a real `<table>` on desktop,
 *   as a stack of cards on mobile. The first column becomes the card title;
 *   remaining columns become key:value rows. Columns tagged
 *   `hideOnMobile` drop off the card entirely.
 * - **Actions dropdown that doesn't clip.** Uses Radix `DropdownMenu` which
 *   portals the menu to `document.body`, escaping any `overflow-x-auto`
 *   scroll container on the table. Fixes the bug where row dropdowns were
 *   cut off or pushed outside the row.
 * - **Per-row action visibility.** Each action can declare `hidden(row)` to
 *   hide itself based on row state (e.g., "Activate" only for inactive
 *   items, "Deactivate" only for active ones). If no action remains visible
 *   for a row, the dropdown is replaced with a "צפייה בלבד" placeholder.
 * - **Loading / error / empty states** built in. Callers just pass the
 *   `useQuery` tuple.
 *
 * See `features/classes/ClassListPage.tsx` for a usage example.
 */
export type Column<T> = {
  /** Column header text (Hebrew). */
  header: string
  /** Cell renderer — receives the row, returns the displayed node. */
  cell: (row: T) => ReactNode
  /** Optional extra classes for the `<td>` (e.g., max-width / truncation). */
  className?: string
  /**
   * On mobile cards, ONE column is the title (shown bold at top). By
   * default that's the first column; pass `primaryMobile: true` to override.
   */
  primaryMobile?: boolean
  /** Skip this column on mobile cards entirely. */
  hideOnMobile?: boolean
}

export type RowAction<T> = {
  /** Menu label (Hebrew). */
  label: string
  /** Invoked when the menu item is clicked. */
  onClick: (row: T) => void
  /** Red-colored destructive variant (e.g., "Cancel"). */
  destructive?: boolean
  /** Return `true` to hide this action for this specific row. */
  hidden?: (row: T) => boolean
}

type DataTableProps<T> = {
  /** Fetched rows. `undefined` is treated as "still loading". */
  data: T[] | undefined
  /** Show the loading state instead of table content. */
  isLoading?: boolean
  /** Render an error message in place of table content. */
  error?: Error | null
  columns: Column<T>[]
  /** Stable identity per row (usually `row.id`). */
  rowKey: (row: T) => string
  /** Available actions per row. Omit entirely for read-only tables. */
  rowActions?: RowAction<T>[]
  /** Hebrew message for the empty state. Default: "אין פריטים להצגה". */
  emptyMessage?: string
  /** Optional click handler for the whole row (usually navigates to detail). */
  onRowClick?: (row: T) => void
  /** If the caller wants to override the default Hebrew "Actions" header. */
  actionsHeader?: string
}

export function DataTable<T>({
  data,
  isLoading,
  error,
  columns,
  rowKey,
  rowActions,
  emptyMessage = "אין פריטים להצגה",
  onRowClick,
  actionsHeader = "פעולות",
}: DataTableProps<T>) {
  const { isMobile } = useDevice()

  if (isLoading) {
    return <div className="py-20 text-center text-gray-400">טוען...</div>
  }
  if (error) {
    return <div className="py-20 text-center text-red-500">{error.message}</div>
  }
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-16 text-center text-sm text-gray-400">
        {emptyMessage}
      </div>
    )
  }

  const showActions = rowActions !== undefined

  if (isMobile) {
    return (
      <div className="space-y-3">
        {data.map((row) => (
          <MobileCard
            key={rowKey(row)}
            row={row}
            columns={columns}
            rowActions={rowActions}
            onRowClick={onRowClick}
          />
        ))}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-right text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            {columns.map((col, i) => (
              <th
                key={i}
                className={`px-5 py-3 font-medium text-gray-500 ${
                  i === 0 ? "rounded-tr-xl" : ""
                } ${!showActions && i === columns.length - 1 ? "rounded-tl-xl" : ""}`}
              >
                {col.header}
              </th>
            ))}
            {showActions && (
              <th className="rounded-tl-xl px-5 py-3 font-medium text-gray-500">
                {actionsHeader}
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={rowKey(row)}
              className={`border-b border-gray-50 transition-colors hover:bg-gray-50/50 ${
                onRowClick ? "cursor-pointer" : ""
              }`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col, i) => (
                <td key={i} className={`px-5 py-3.5 ${col.className ?? ""}`}>
                  {col.cell(row)}
                </td>
              ))}
              {showActions && (
                // stopPropagation on the actions cell so opening the
                // dropdown (or clicking an item) doesn't also trigger the
                // row-level navigate handler. Regular cells don't need it —
                // plain text/badges should bubble up to onRowClick.
                <td className="px-5 py-3.5" onClick={(e) => e.stopPropagation()}>
                  <ActionsMenu row={row} actions={rowActions!} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Mobile card ─────────────────────────────────────────────── */

function MobileCard<T>({
  row,
  columns,
  rowActions,
  onRowClick,
}: {
  row: T
  columns: Column<T>[]
  rowActions?: RowAction<T>[]
  onRowClick?: (row: T) => void
}) {
  const primaryIdx = columns.findIndex((c) => c.primaryMobile) ?? -1
  const primary = columns[primaryIdx === -1 ? 0 : primaryIdx]
  const rest = columns.filter(
    (c, i) => i !== (primaryIdx === -1 ? 0 : primaryIdx) && !c.hideOnMobile,
  )
  const showActions = rowActions !== undefined

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div
        className={onRowClick ? "cursor-pointer" : ""}
        onClick={onRowClick ? () => onRowClick(row) : undefined}
      >
        <div className="font-semibold text-gray-900">{primary.cell(row)}</div>
        <div className="mt-2 space-y-1 text-xs">
          {rest.map((c, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-gray-400">{c.header}:</span>
              <span className="min-w-0 flex-1 text-gray-700">{c.cell(row)}</span>
            </div>
          ))}
        </div>
      </div>
      {showActions && (
        <div className="mt-3 border-t border-gray-100 pt-3">
          <ActionsMenu row={row} actions={rowActions!} />
        </div>
      )}
    </div>
  )
}

/* ── Actions dropdown (Radix) ───────────────────────────────── */

function ActionsMenu<T>({ row, actions }: { row: T; actions: RowAction<T>[] }) {
  const visible = actions.filter((a) => !a.hidden?.(row))

  if (visible.length === 0) {
    return <span className="text-xs text-gray-400">צפייה בלבד</span>
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50">
          פעולות ▾
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[140px]">
        {visible.map((action, i) => (
          <DropdownMenuItem
            key={i}
            variant={action.destructive ? "destructive" : "default"}
            onSelect={() => action.onClick(row)}
            className="justify-end text-right"
          >
            {action.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/* ── Convenience hook for the common "row click → detail page" case ─── */

/**
 * Returns a navigate-to-detail handler for the given route template.
 * Usage: `onRowClick={useRowClickNavigator((row) => `/members/${row.id}`)}`
 */
export function useRowClickNavigator<T>(buildPath: (row: T) => string) {
  const navigate = useNavigate()
  return (row: T) => navigate(buildPath(row))
}
