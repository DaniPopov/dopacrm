import "@testing-library/jest-dom/vitest"
import { vi } from "vitest"

/**
 * jsdom doesn't ship `window.matchMedia`. Provide a minimal stub so any
 * component using `useDevice()` works in tests. Default to a desktop
 * viewport — tests that specifically exercise mobile/tablet layouts
 * override this.
 */
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("min-width: 1024px") || query.includes("min-width: 768px"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}
