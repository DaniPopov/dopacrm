import { describe, it, expect, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { DataTable, type Column, type RowAction } from "./data-table"

type Row = { id: string; name: string; active: boolean }

const rows: Row[] = [
  { id: "1", name: "Alpha", active: true },
  { id: "2", name: "Beta", active: false },
]

const columns: Column<Row>[] = [
  { header: "שם", cell: (r) => r.name, primaryMobile: true },
  {
    header: "סטטוס",
    cell: (r) => (r.active ? "פעיל" : "לא פעיל"),
  },
]

function renderTable(props: Partial<Parameters<typeof DataTable<Row>>[0]> = {}) {
  return render(
    <MemoryRouter>
      <DataTable<Row>
        data={rows}
        columns={columns}
        rowKey={(r) => r.id}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe("DataTable", () => {
  it("renders a loading placeholder when isLoading=true", () => {
    renderTable({ data: undefined, isLoading: true })
    expect(screen.getByText("טוען...")).toBeInTheDocument()
  })

  it("renders the error message", () => {
    renderTable({ data: undefined, error: new Error("boom") })
    expect(screen.getByText("boom")).toBeInTheDocument()
  })

  it("renders the empty state", () => {
    renderTable({ data: [] })
    expect(screen.getByText("אין פריטים להצגה")).toBeInTheDocument()
  })

  it("shows a custom emptyMessage when provided", () => {
    renderTable({ data: [], emptyMessage: "אין מסלולים" })
    expect(screen.getByText("אין מסלולים")).toBeInTheDocument()
  })

  it("renders rows with column cells", () => {
    renderTable()
    expect(screen.getByText("Alpha")).toBeInTheDocument()
    expect(screen.getByText("Beta")).toBeInTheDocument()
    expect(screen.getByText("פעיל")).toBeInTheDocument()
  })

  it("calls onRowClick when a row is clicked", async () => {
    const onRowClick = vi.fn()
    const user = userEvent.setup()
    renderTable({ onRowClick })
    await user.click(screen.getByText("Alpha"))
    expect(onRowClick).toHaveBeenCalledWith(rows[0])
  })

  it("does NOT render an actions column when rowActions is undefined", () => {
    renderTable()
    expect(screen.queryByText("פעולות")).not.toBeInTheDocument()
  })

  it("renders 'צפייה בלבד' placeholder for all rows when rowActions is []", () => {
    renderTable({ rowActions: [] })
    // Two rows, one placeholder each
    const placeholders = screen.getAllByText("צפייה בלבד")
    expect(placeholders).toHaveLength(2)
  })

  it("shows the dropdown trigger when there are visible actions", () => {
    const actions: RowAction<Row>[] = [
      { label: "עריכה", onClick: vi.fn() },
    ]
    renderTable({ rowActions: actions })
    expect(screen.getAllByRole("button", { name: /פעולות/ })).toHaveLength(2)
  })

  it("hidden(row) filters actions per-row", async () => {
    const onDeactivate = vi.fn()
    const onActivate = vi.fn()
    const actions: RowAction<Row>[] = [
      {
        label: "השבתה",
        onClick: onDeactivate,
        hidden: (r) => !r.active,
      },
      {
        label: "הפעלה",
        onClick: onActivate,
        hidden: (r) => r.active,
      },
    ]
    const user = userEvent.setup()
    renderTable({ rowActions: actions })

    // Open the first row's menu (active) → should show השבתה, not הפעלה
    const triggers = screen.getAllByRole("button", { name: /פעולות/ })
    await user.click(triggers[0])
    expect(screen.getByText("השבתה")).toBeInTheDocument()
    expect(screen.queryByText("הפעלה")).not.toBeInTheDocument()
  })

  it("stopsPropagation from the actions cell so row-click doesn't also fire", async () => {
    const onRowClick = vi.fn()
    const onAction = vi.fn()
    const actions: RowAction<Row>[] = [{ label: "X", onClick: onAction }]
    const user = userEvent.setup()
    renderTable({ rowActions: actions, onRowClick })

    const triggers = screen.getAllByRole("button", { name: /פעולות/ })
    await user.click(triggers[0])
    // Opening the menu should NOT have triggered onRowClick
    expect(onRowClick).not.toHaveBeenCalled()
  })

  it("shows 'צפייה בלבד' when every action is hidden for a given row", () => {
    const actions: RowAction<Row>[] = [
      { label: "עריכה", onClick: vi.fn(), hidden: () => true },
    ]
    renderTable({ rowActions: actions })
    const placeholders = screen.getAllByText("צפייה בלבד")
    expect(placeholders).toHaveLength(2)
  })
})
