import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { TemplatesList } from "./TemplatesList"
import type { ScheduleTemplate } from "./types"

vi.mock("./hooks", () => ({
  useTemplates: vi.fn(),
  useDeactivateTemplate: vi.fn(),
}))

import { useTemplates, useDeactivateTemplate } from "./hooks"
const mockUseTemplates = vi.mocked(useTemplates)
const mockUseDeactivate = vi.mocked(useDeactivateTemplate)

const tpl: ScheduleTemplate = {
  id: "tpl1",
  tenant_id: "t1",
  class_id: "c1",
  weekdays: ["sun", "tue"],
  start_time: "18:00:00",
  end_time: "19:00:00",
  head_coach_id: "k1",
  assistant_coach_id: null,
  starts_on: "2026-01-01",
  ends_on: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

const classes = [
  {
    id: "c1",
    tenant_id: "t1",
    name: "Boxing",
    description: null,
    color: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

const coaches = [
  {
    id: "k1",
    tenant_id: "t1",
    user_id: null,
    first_name: "David",
    last_name: "Cohen",
    phone: null,
    email: null,
    hired_at: "2026-01-01",
    status: "active" as const,
    frozen_at: null,
    cancelled_at: null,
    custom_attrs: {},
    tenant_features_enabled: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <TemplatesList classes={classes} coaches={coaches} />
    </QueryClientProvider>,
  )
}

describe("TemplatesList", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseDeactivate.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      reset: vi.fn(),
    } as never)
  })

  it("shows count badge", () => {
    mockUseTemplates.mockReturnValue({
      data: [tpl, { ...tpl, id: "tpl2" }],
      isLoading: false,
    } as never)
    renderList()
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("hides templates by default (collapsed)", () => {
    mockUseTemplates.mockReturnValue({ data: [tpl], isLoading: false } as never)
    renderList()
    expect(screen.queryByText("Boxing")).not.toBeInTheDocument()
  })

  it("expands on click to show templates", async () => {
    mockUseTemplates.mockReturnValue({ data: [tpl], isLoading: false } as never)
    renderList()
    await userEvent.click(screen.getByRole("button", { name: /תבניות פעילות/ }))
    expect(screen.getByText("Boxing")).toBeInTheDocument()
    // Hebrew weekday letters in the meta line.
    expect(screen.getByText(/א, ג/)).toBeInTheDocument()
    // Coach name.
    expect(screen.getByText(/David Cohen/)).toBeInTheDocument()
  })

  it("shows empty-state when no templates", async () => {
    mockUseTemplates.mockReturnValue({ data: [], isLoading: false } as never)
    renderList()
    await userEvent.click(screen.getByRole("button", { name: /תבניות פעילות/ }))
    expect(screen.getByText(/אין תבניות פעילות/)).toBeInTheDocument()
  })

  it("clicking השבת opens confirm dialog", async () => {
    mockUseTemplates.mockReturnValue({ data: [tpl], isLoading: false } as never)
    renderList()
    await userEvent.click(screen.getByRole("button", { name: /תבניות פעילות/ }))
    await userEvent.click(screen.getByRole("button", { name: "השבת" }))
    expect(
      screen.getByText(/התבנית תושבת ושיעורים עתידיים/),
    ).toBeInTheDocument()
  })

  it("confirm calls deactivate mutation with template id", async () => {
    const mutate = vi.fn()
    mockUseDeactivate.mockReturnValue({
      mutate,
      isPending: false,
      reset: vi.fn(),
    } as never)
    mockUseTemplates.mockReturnValue({ data: [tpl], isLoading: false } as never)
    renderList()
    await userEvent.click(screen.getByRole("button", { name: /תבניות פעילות/ }))
    await userEvent.click(screen.getByRole("button", { name: "השבת" }))
    await userEvent.click(screen.getByRole("button", { name: "כן, השבת" }))
    expect(mutate).toHaveBeenCalledWith(
      "tpl1",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })
})
