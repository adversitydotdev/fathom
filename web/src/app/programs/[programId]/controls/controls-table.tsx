"use client";

import { usePathname, useRouter } from "next/navigation";

import { useListLocation } from "@/components/shell/side-panel";
import { useMemo } from "react";
import { cn } from "cn";

import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { AgentMark, CONTROL_STATES, ControlStateBadge, controlStateLabel } from "@/components/status";
import type { ControlState, Implementation } from "@/lib/api/types";

export type ControlRow = {
  id: string;
  displayId: string;
  name: string;
  family: string;
  state: ControlState;
  failed: string[];
  implStatus?: Implementation["status"];
  owner?: string;
  byAgent: boolean;
};

/** Gaps first, then the rest. Also the sort key for the state column. */
const ORDER: Record<ControlState, number> = { gap: 0, waived: 1, met: 2, out_of_scope: 3 };

const columns: DataTableColumn<ControlRow>[] = [
  { id: "displayId", header: "Id", width: 88, sortable: true, cell: (r) => <span className="font-mono text-xs">{r.displayId}</span> },
  {
    id: "name",
    header: "Control",
    sortable: true,
    cell: (r) => (
      <span className="block min-w-0">
        <span className="flex items-center gap-1.5">
          <span className="truncate">{r.name}</span>
          {r.byAgent && <AgentMark />}
        </span>
        <span className="block truncate text-xs text-muted-foreground">{r.family}</span>
        {r.failed[0] && <span className="block truncate text-xs text-gap-ink @[64rem]/datatable:hidden">{r.failed[0]}</span>}
      </span>
    ),
  },
  { id: "state", header: "State", width: 128, sortable: true, value: (r) => ORDER[r.state], cell: (r) => <ControlStateBadge state={r.state} /> },
  {
    id: "failed",
    header: "Failed condition",
    hideBelow: "lg",
    value: (r) => r.failed.join(" "),
    cell: (r) =>
      r.failed.length ? (
        <span className="block truncate text-xs text-gap-ink" title={r.failed.join("\n")}>
          {r.failed[0]}
          {r.failed.length > 1 && <span className="text-muted-foreground"> +{r.failed.length - 1}</span>}
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
  {
    id: "implStatus",
    header: "Implementation",
    width: 128,
    hideBelow: "lg",
    sortable: true,
    cell: (r) => <span className="font-mono text-xs text-muted-foreground">{r.implStatus ?? "none"}</span>,
  },
  { id: "owner", header: "Owner", width: 160, hideBelow: "lg", sortable: true, cell: (r) => <span className="truncate text-muted-foreground">{r.owner ?? "—"}</span> },
];

export function ControlsTable({ rows, programId, at }: { rows: ControlRow[]; programId: string; at?: string }) {
  const router = useRouter();
  const current = usePathname();
  const { pathname, search } = useListLocation();
  const state = search.get("state") as ControlState | null;
  const family = search.get("family");

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next}`, { scroll: false });
  };

  const counts = useMemo(() => {
    const c = Object.fromEntries(CONTROL_STATES.map((s) => [s, 0])) as Record<ControlState, number>;
    for (const r of rows) c[r.state]++;
    return c;
  }, [rows]);
  const families = useMemo(() => [...new Set(rows.map((r) => r.family))].sort(), [rows]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (!state || r.state === state) && (!family || r.family === family))
        .sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.displayId.localeCompare(b.displayId)),
    [rows, state, family],
  );

  return (
    <DataTable
      data={visible}
      columns={columns}
      rowId={(r) => r.id}
      rowLabel={(r) => `${r.displayId} ${r.name}`}
      caption="Controls on the program's baseline with their computed state"
      searchable
      searchPlaceholder="Search controls"
      searchText={(r) => `${r.displayId} ${r.name} ${r.family} ${r.owner ?? ""} ${r.id}`}
      clipboard={false}
      isRowActive={(r) => current.endsWith(`/controls/${r.id}`)}
      onRowClick={(r) => router.push(`/programs/${programId}/controls/${r.id}${at ? `?at=${at}` : ""}`)}
      emptyState={<span className="text-sm text-muted-foreground">No controls match these filters.</span>}
      toolbar={
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!state} onClick={() => setParam("state", null)}>
            All {rows.length}
          </Chip>
          {CONTROL_STATES.map((s) => (
            <Chip key={s} active={state === s} onClick={() => setParam("state", state === s ? null : s)}>
              {controlStateLabel(s)} {counts[s]}
            </Chip>
          ))}
          <select
            aria-label="Family"
            value={family ?? ""}
            onChange={(e) => setParam("family", e.target.value || null)}
            className="h-7 rounded-full border bg-transparent px-2.5 text-xs text-muted-foreground"
          >
            <option value="">All families</option>
            {families.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
      }
    />
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "h-7 rounded-full border px-3 text-xs text-muted-foreground transition-colors hover:text-foreground",
        active && "border-foreground/40 bg-muted text-foreground",
      )}
    >
      {children}
    </button>
  );
}
