import { useSyncExternalStore } from "react"

/**
 * Device-size detection — mobile / tablet / desktop.
 *
 * Breakpoints (aligned with Tailwind's defaults):
 *   - mobile:  width <  768px   (phones)
 *   - tablet:  width <  1024px  (iPad portrait, small front-desk screens)
 *   - desktop: width >= 1024px  (laptops, wide front-desk monitors)
 *
 * Implemented via `window.matchMedia` so changes (rotation, window resize,
 * dev-tools mobile toggle) trigger a re-render. Uses `useSyncExternalStore`
 * — the React 19 idiom for subscribing to browser APIs.
 *
 * Use this when CSS-only responsive (`sm:` / `lg:` Tailwind prefixes) isn't
 * enough — for example, rendering a card list on mobile but a table on
 * desktop, or swapping a fixed sidebar for a drawer.
 *
 * @example
 *   const { isMobile, isTablet, isDesktop, type } = useDevice()
 *   return isMobile ? <CardList /> : <Table />
 */
export type DeviceType = "mobile" | "tablet" | "desktop"

const TABLET_MIN_PX = 768
const DESKTOP_MIN_PX = 1024

const tabletQuery = `(min-width: ${TABLET_MIN_PX}px)`
const desktopQuery = `(min-width: ${DESKTOP_MIN_PX}px)`

function getSnapshot(): DeviceType {
  if (typeof window === "undefined") return "desktop" // SSR fallback (we're SPA so unused, but safe)
  if (window.matchMedia(desktopQuery).matches) return "desktop"
  if (window.matchMedia(tabletQuery).matches) return "tablet"
  return "mobile"
}

/** Subscribe to viewport-size changes; React calls this once. */
function subscribe(notify: () => void): () => void {
  const tabletMql = window.matchMedia(tabletQuery)
  const desktopMql = window.matchMedia(desktopQuery)
  tabletMql.addEventListener("change", notify)
  desktopMql.addEventListener("change", notify)
  return () => {
    tabletMql.removeEventListener("change", notify)
    desktopMql.removeEventListener("change", notify)
  }
}

export function useDevice() {
  const type = useSyncExternalStore(subscribe, getSnapshot, () => "desktop" as DeviceType)
  return {
    type,
    isMobile: type === "mobile",
    isTablet: type === "tablet",
    isDesktop: type === "desktop",
  }
}
