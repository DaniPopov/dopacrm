import { describe, it, expect, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AsyncCombobox } from "./async-combobox"

type Item = { id: string; label: string }

const ALL: Item[] = Array.from({ length: 12 }, (_, i) => ({
  id: String(i + 1),
  label: `Item ${i + 1}`,
}))

function makeLoader(pageSize: number) {
  return vi.fn(async ({ search, offset }: { search: string; offset: number }) => {
    const filtered = search
      ? ALL.filter((i) => i.label.toLowerCase().includes(search.toLowerCase()))
      : ALL
    return filtered.slice(offset, offset + pageSize)
  })
}

function Wrapper({ loader, pageSize = 5 }: { loader: ReturnType<typeof makeLoader>; pageSize?: number }) {
  return (
    <AsyncCombobox<Item>
      value={null}
      onChange={() => {}}
      loadItems={loader}
      getKey={(i) => i.id}
      getLabel={(i) => i.label}
      renderItem={(i) => <span>{i.label}</span>}
      placeholder="חיפוש"
      pageSize={pageSize}
      loadMoreLabel="עוד"
    />
  )
}

describe("AsyncCombobox", () => {
  it("fetches page 1 when opened and renders items", async () => {
    const loader = makeLoader(5)
    render(<Wrapper loader={loader} />)

    await userEvent.click(screen.getByRole("button"))

    await waitFor(() => {
      expect(screen.getByText("Item 1")).toBeInTheDocument()
      expect(screen.getByText("Item 5")).toBeInTheDocument()
    })
    expect(screen.queryByText("Item 6")).not.toBeInTheDocument()
    expect(loader).toHaveBeenCalledWith({ search: "", limit: 5, offset: 0 })
  })

  it("loads more on 'load more' click", async () => {
    const loader = makeLoader(5)
    render(<Wrapper loader={loader} />)

    await userEvent.click(screen.getByRole("button"))
    await waitFor(() => screen.getByText("Item 1"))

    await userEvent.click(screen.getByRole("button", { name: "עוד" }))

    await waitFor(() => {
      expect(screen.getByText("Item 6")).toBeInTheDocument()
    })
    expect(loader).toHaveBeenCalledWith({ search: "", limit: 5, offset: 5 })
  })

  it("filters items when the user types", async () => {
    const loader = makeLoader(5)
    render(<Wrapper loader={loader} />)

    await userEvent.click(screen.getByRole("button"))
    await waitFor(() => screen.getByText("Item 1"))

    const input = screen.getByPlaceholderText("חיפוש")
    await userEvent.type(input, "12")

    await waitFor(() => {
      expect(loader).toHaveBeenCalledWith({ search: "12", limit: 5, offset: 0 })
    })
  })

  it("calls onChange and closes when an item is selected", async () => {
    const loader = makeLoader(5)
    const onChange = vi.fn()

    render(
      <AsyncCombobox<Item>
        value={null}
        onChange={onChange}
        loadItems={loader}
        getKey={(i) => i.id}
        getLabel={(i) => i.label}
        renderItem={(i) => <span>{i.label}</span>}
      />,
    )

    await userEvent.click(screen.getByRole("button"))
    await waitFor(() => screen.getByText("Item 1"))

    await userEvent.click(screen.getByText("Item 2"))

    expect(onChange).toHaveBeenCalledWith(ALL[1])
    await waitFor(() => {
      expect(screen.queryByText("Item 1")).not.toBeInTheDocument()
    })
  })

  it("shows empty state when loader returns no items", async () => {
    const loader = vi.fn(async () => [] as Item[])
    render(
      <AsyncCombobox<Item>
        value={null}
        onChange={() => {}}
        loadItems={loader}
        getKey={(i) => i.id}
        getLabel={(i) => i.label}
        renderItem={(i) => <span>{i.label}</span>}
        emptyLabel="NONE"
      />,
    )

    await userEvent.click(screen.getByRole("button"))
    await waitFor(() => expect(screen.getByText("NONE")).toBeInTheDocument())
  })
})
