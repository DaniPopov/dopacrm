import { describe, it, expect, beforeEach, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useDevice } from "./useDevice"

/**
 * Mock window.matchMedia — jsdom doesn't ship one. We control which media
 * queries match by tracking width and comparing against the queries.
 */
function setViewport(width: number) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>()

  window.matchMedia = vi.fn().mockImplementation((query: string) => {
    const minMatch = query.match(/min-width:\s*(\d+)px/)
    const minWidth = minMatch ? parseInt(minMatch[1], 10) : 0
    const matches = width >= minWidth
    return {
      matches,
      media: query,
      addEventListener: (_event: string, listener: (e: MediaQueryListEvent) => void) =>
        listeners.add(listener),
      removeEventListener: (_event: string, listener: (e: MediaQueryListEvent) => void) =>
        listeners.delete(listener),
      dispatchEvent: () => true,
    } as unknown as MediaQueryList
  })
}

describe("useDevice", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("reports mobile below 768px", () => {
    setViewport(375)
    const { result } = renderHook(() => useDevice())
    expect(result.current.type).toBe("mobile")
    expect(result.current.isMobile).toBe(true)
    expect(result.current.isTablet).toBe(false)
    expect(result.current.isDesktop).toBe(false)
  })

  it("reports tablet between 768px and 1023px", () => {
    setViewport(900)
    const { result } = renderHook(() => useDevice())
    expect(result.current.type).toBe("tablet")
    expect(result.current.isTablet).toBe(true)
    expect(result.current.isMobile).toBe(false)
    expect(result.current.isDesktop).toBe(false)
  })

  it("reports desktop at 1024px and above", () => {
    setViewport(1440)
    const { result } = renderHook(() => useDevice())
    expect(result.current.type).toBe("desktop")
    expect(result.current.isDesktop).toBe(true)
    expect(result.current.isMobile).toBe(false)
    expect(result.current.isTablet).toBe(false)
  })

  it("treats exactly 768px as tablet", () => {
    setViewport(768)
    const { result } = renderHook(() => useDevice())
    expect(result.current.type).toBe("tablet")
  })

  it("treats exactly 1024px as desktop", () => {
    setViewport(1024)
    const { result } = renderHook(() => useDevice())
    expect(result.current.type).toBe("desktop")
  })

  it("re-renders when viewport changes (subscription works)", () => {
    setViewport(375)
    const { result, rerender } = renderHook(() => useDevice())
    expect(result.current.type).toBe("mobile")

    act(() => {
      setViewport(1440)
    })
    rerender()
    expect(result.current.type).toBe("desktop")
  })
})
