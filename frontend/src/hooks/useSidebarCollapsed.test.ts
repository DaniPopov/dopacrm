import { describe, it, expect, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useSidebarCollapsed } from "./useSidebarCollapsed"

const KEY = "dopacrm.sidebar.collapsed"

describe("useSidebarCollapsed", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("defaults to false when localStorage is empty", () => {
    const { result } = renderHook(() => useSidebarCollapsed())
    const [collapsed] = result.current
    expect(collapsed).toBe(false)
  })

  it("reads the initial value from localStorage", () => {
    window.localStorage.setItem(KEY, "true")
    const { result } = renderHook(() => useSidebarCollapsed())
    const [collapsed] = result.current
    expect(collapsed).toBe(true)
  })

  it("toggle flips the value and persists it", () => {
    const { result } = renderHook(() => useSidebarCollapsed())

    act(() => {
      const [, toggle] = result.current
      toggle()
    })

    expect(result.current[0]).toBe(true)
    expect(window.localStorage.getItem(KEY)).toBe("true")

    act(() => {
      const [, toggle] = result.current
      toggle()
    })

    expect(result.current[0]).toBe(false)
    expect(window.localStorage.getItem(KEY)).toBe("false")
  })

  it("does not re-read localStorage on subsequent renders", () => {
    const { result, rerender } = renderHook(() => useSidebarCollapsed())
    act(() => result.current[1]())
    // External write after mount shouldn't affect the hook
    window.localStorage.setItem(KEY, "false")
    rerender()
    expect(result.current[0]).toBe(true)
  })
})
