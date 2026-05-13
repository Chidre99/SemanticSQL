import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useState } from "react";

type Props = {
  columns: string[];
  rows: Record<string, unknown>[];
  elapsedMs: number | null;
};

export default function ResultsTable({ columns, rows, elapsedMs }: Props) {
  // If columns aren't yet known (mid-stream), derive from the first row.
  const cols = useMemo(() => {
    if (columns?.length) return columns;
    if (rows.length) return Object.keys(rows[0]);
    return [];
  }, [columns, rows]);

  const colDefs = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      cols.map((c) => ({
        id: c,
        accessorFn: (row) => row[c],
        header: c,
        cell: (info) => formatCell(info.getValue()),
      })),
    [cols]
  );

  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data: rows,
    columns: colDefs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!rows.length && !cols.length) {
    return <div className="text-ink-faint text-sm italic px-1">No results yet.</div>;
  }

  return (
    <div className="flex flex-col gap-2 min-h-0 flex-1">
      <div className="flex items-center justify-between text-xs text-ink-muted px-1">
        <span className="uppercase tracking-wider">Results</span>
        <span>
          {rows.length} row{rows.length === 1 ? "" : "s"}
          {elapsedMs != null && <> · {elapsedMs.toLocaleString()} ms</>}
        </span>
      </div>
      <div className="border border-bg-soft rounded-md overflow-auto flex-1 min-h-[10rem]">
        <table className="min-w-full text-xs font-mono">
          <thead className="bg-bg-soft sticky top-0">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    onClick={h.column.getToggleSortingHandler()}
                    className="px-3 py-2 text-left font-medium text-ink-muted whitespace-nowrap cursor-pointer select-none hover:text-ink"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr key={row.id} className={i % 2 === 0 ? "bg-transparent" : "bg-bg-soft/40"}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-1.5 whitespace-nowrap text-ink">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
