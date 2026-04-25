/**
 * Focused tests for the substitute-pay reveal logic on
 * BulkActionDialog. Full happy-path is covered by the backend E2E
 * tests; here we lock in the FE branch that decides whether the
 * pay form needs to appear.
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BulkActionDialog } from "./BulkActionDialog"

vi.mock("./hooks", () => ({
  useBulkAction: vi.fn(),
}))
vi.mock("@/features/coaches/hooks", () => ({
  useCoachesForClass: vi.fn(),
}))
vi.mock("@/features/classes/api", () => ({
  listClasses: vi.fn(),
}))
vi.mock("@/features/coaches/api", () => ({
  listCoaches: vi.fn(),
}))

import { useBulkAction } from "./hooks"
import { useCoachesForClass } from "@/features/coaches/hooks"
import { listClasses } from "@/features/classes/api"
import { listCoaches } from "@/features/coaches/api"

const mockUseBulkAction = vi.mocked(useBulkAction)
const mockUseCoachesForClass = vi.mocked(useCoachesForClass)
const mockListClasses = vi.mocked(listClasses)
const mockListCoaches = vi.mocked(listCoaches)

const cls = {
  id: "c1",
  tenant_id: "t1",
  name: "Boxing",
  description: null,
  color: null,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}
const coach = {
  id: "k1",
  tenant_id: "t1",
  user_id: null,
  first_name: "Yoni",
  last_name: "Levi",
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
}

function setup(opts: { classCoachLinks?: unknown[] } = {}) {
  mockListClasses.mockResolvedValue([cls])
  mockListCoaches.mockResolvedValue([coach])
  mockUseCoachesForClass.mockReturnValue({
    data: opts.classCoachLinks ?? [],
    isLoading: false,
  } as never)
  mockUseBulkAction.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
    reset: vi.fn(),
  } as never)

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <BulkActionDialog onClose={() => {}} />
    </QueryClientProvider>,
  )
}

async function pickClass() {
  // The combobox trigger is the first button without a name.
  const triggers = screen.getAllByRole("button")
  // First combobox trigger renders the placeholder.
  await userEvent.click(triggers.find((b) => b.textContent?.includes("בחרו שיעור")) as HTMLElement)
  await waitFor(() => screen.getByText("Boxing"))
  await userEvent.click(screen.getByText("Boxing"))
}

async function setRange() {
  const dateInputs = document
    .querySelectorAll('input[type="date"]') as NodeListOf<HTMLInputElement>
  await userEvent.type(dateInputs[0], "2026-06-01")
  await userEvent.type(dateInputs[1], "2026-06-07")
}

async function pickSwapAndCoach() {
  await userEvent.selectOptions(
    screen.getByDisplayValue("בטל את כל השיעורים בטווח"),
    "swap_coach",
  )
  const triggers = screen.getAllByRole("button")
  await userEvent.click(triggers.find((b) => b.textContent?.includes("בחרו מאמן")) as HTMLElement)
  await waitFor(() => screen.getByText("Yoni Levi"))
  await userEvent.click(screen.getByText("Yoni Levi"))
}

describe("BulkActionDialog — substitute-pay reveal", () => {
  beforeEach(() => vi.clearAllMocks())

  it("does NOT show substitute-pay form for action=cancel", async () => {
    setup()
    await pickClass()
    await setRange()
    // action defaults to cancel; pay form should be absent.
    expect(screen.queryByText(/למאמן זה אין תעריף/)).not.toBeInTheDocument()
  })

  it("shows substitute-pay form when swap_coach + new coach has no rate", async () => {
    setup({ classCoachLinks: [] }) // no existing links
    await pickClass()
    await setRange()
    await pickSwapAndCoach()
    expect(
      screen.getByText(/למאמן זה אין תעריף עבור השיעור הזה/),
    ).toBeInTheDocument()
  })

  it("hides substitute-pay form when new coach already has a rate covering range", async () => {
    setup({
      classCoachLinks: [
        {
          id: "l1",
          tenant_id: "t1",
          class_id: "c1",
          coach_id: "k1", // Yoni
          role: "עוזר",
          is_primary: false,
          pay_model: "per_session",
          pay_amount_cents: 3000,
          weekdays: [],
          starts_on: "2026-01-01",
          ends_on: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    })
    await pickClass()
    await setRange()
    await pickSwapAndCoach()
    expect(screen.queryByText(/למאמן זה אין תעריף/)).not.toBeInTheDocument()
  })
})
