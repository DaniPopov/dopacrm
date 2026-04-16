import { useCallback, useEffect, useState } from "react"

const STORAGE_KEY = "dopacrm.sidebar.collapsed"

/**
 * Persist the desktop sidebar collapse state across reloads.
 *
 * Reads the initial value from ``localStorage`` on mount (default: false)
 * and writes every change back. Mobile uses its own drawer open/close
 * state and ignores this hook.
 *
 * @returns `[collapsed, toggle]` — tuple of the current state and a
 *          toggle function.
 */
export function useSidebarCollapsed(): readonly [boolean, () => void] {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false
    return window.localStorage.getItem(STORAGE_KEY) === "true"
  })

  useEffect(() => {
    if (typeof window === "undefined") return
    window.localStorage.setItem(STORAGE_KEY, String(collapsed))
  }, [collapsed])

  const toggle = useCallback(() => {
    setCollapsed((v) => !v)
  }, [])

  return [collapsed, toggle] as const
}
