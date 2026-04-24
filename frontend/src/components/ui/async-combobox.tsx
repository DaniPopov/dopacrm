import { useEffect, useMemo, useRef, useState } from "react"
import { Popover as PopoverPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

/**
 * Generic async combobox — portal-positioned dropdown with search +
 * pagination. Shared primitive for pages that need "pick one from a
 * potentially-long list" (members, classes, plans, ...).
 *
 * Generic: pass in any item type + the three extractor callbacks.
 *
 * Behavior:
 * - Click/focus the trigger → dropdown opens, shows page 1.
 * - Typing filters via the caller's ``loadItems({ search, limit, offset })``.
 * - Scroll past the list or click "load more" to fetch the next page.
 * - Select → calls ``onChange`` with the item + closes the dropdown.
 *
 * Portal-based (Radix Popover) — never clipped by parent overflow.
 */
export type AsyncComboboxProps<T> = {
  /** Currently selected item. Shown as a chip inside the trigger. */
  value: T | null
  onChange: (item: T | null) => void
  /** Paginated fetch. Stable identity preferred (memoize with useCallback). */
  loadItems: (args: { search: string; limit: number; offset: number }) => Promise<T[]>
  getKey: (item: T) => string
  renderItem: (item: T) => React.ReactNode
  /** Plain-text label for the selected chip + aria. */
  getLabel: (item: T) => string
  placeholder?: string
  /** Page size — default 10. */
  pageSize?: number
  emptyLabel?: string
  loadingLabel?: string
  loadMoreLabel?: string
  className?: string
  disabled?: boolean
  /** Accessible label, used by screen readers on the trigger. */
  ariaLabel?: string
}

export function AsyncCombobox<T>({
  value,
  onChange,
  loadItems,
  getKey,
  renderItem,
  getLabel,
  placeholder = "חיפוש...",
  pageSize = 10,
  emptyLabel = "אין תוצאות",
  loadingLabel = "טוען...",
  loadMoreLabel = "טען עוד",
  className,
  disabled,
  ariaLabel,
}: AsyncComboboxProps<T>) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [items, setItems] = useState<T[]>([])
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Fetch on open + on search change (debounced). Resets pagination.
  useEffect(() => {
    if (!open) return
    let cancelled = false
    const run = async () => {
      setLoading(true)
      try {
        const data = await loadItems({ search, limit: pageSize, offset: 0 })
        if (cancelled) return
        setItems(data)
        setPage(0)
        setHasMore(data.length === pageSize)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    const t = setTimeout(run, 180)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [open, search, loadItems, pageSize])

  // Focus the search box when the popover opens.
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => searchInputRef.current?.focus(), 20)
      return () => clearTimeout(t)
    }
  }, [open])

  async function loadMore() {
    setLoading(true)
    try {
      const next = page + 1
      const data = await loadItems({
        search,
        limit: pageSize,
        offset: next * pageSize,
      })
      setItems((prev) => [...prev, ...data])
      setPage(next)
      setHasMore(data.length === pageSize)
    } finally {
      setLoading(false)
    }
  }

  const triggerLabel = useMemo(() => {
    if (value) return getLabel(value)
    return placeholder
  }, [value, getLabel, placeholder])

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild disabled={disabled}>
        <button
          type="button"
          aria-label={ariaLabel}
          className={cn(
            "flex w-full items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2 text-right text-sm outline-none transition-all hover:bg-gray-50 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50",
            className,
          )}
        >
          <span className={cn("truncate", !value && "text-gray-400")}>
            {triggerLabel}
          </span>
          <ChevronDown className="h-4 w-4 text-gray-400" />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="end"
          sideOffset={6}
          className="z-50 w-[var(--radix-popover-trigger-width)] min-w-[16rem] rounded-lg border border-gray-200 bg-white shadow-lg"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className="border-b border-gray-100 p-2">
            <input
              ref={searchInputRef}
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={placeholder}
              className="w-full rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm outline-none placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {loading && items.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-gray-400">
                {loadingLabel}
              </div>
            ) : items.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-gray-400">
                {emptyLabel}
              </div>
            ) : (
              <>
                <ul role="listbox">
                  {items.map((item) => {
                    const key = getKey(item)
                    const isSelected = value != null && getKey(value) === key
                    return (
                      <li key={key}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={isSelected}
                          onClick={() => {
                            onChange(item)
                            setOpen(false)
                          }}
                          className={cn(
                            "flex w-full items-center rounded-md px-2 py-1.5 text-right text-sm transition-colors hover:bg-gray-50",
                            isSelected && "bg-blue-50 text-blue-900",
                          )}
                        >
                          {renderItem(item)}
                        </button>
                      </li>
                    )
                  })}
                </ul>
                {hasMore && (
                  <button
                    type="button"
                    onClick={loadMore}
                    disabled={loading}
                    className="mt-1 w-full rounded-md px-2 py-1.5 text-xs font-medium text-blue-600 transition-colors hover:bg-blue-50 disabled:opacity-50"
                  >
                    {loading ? loadingLabel : loadMoreLabel}
                  </button>
                )}
              </>
            )}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}
