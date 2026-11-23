"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useListLocation } from "@/components/shell/side-panel";
import { useMemo } from "react";
import { cn } from "cn";

import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { REQUIREMENT_STATES, RequirementStateBadge } from "@/components/status";
import type { RequirementState } from "@/lib/api/types";

export type RequirementRow = {
  id: string;
  displayId: string;
  name: string;
  frameworkId: string;
  frameworkName: string;
  state: RequirementState;
  controls: { id: string; displayId: string }[];
  unmetCount: number;
};

const ORDER: Record<RequirementState, number> = { gap: 0, contribution: 1, unmapped: 2, covered: 3 };

export function RequirementsTable({
  rows,
  frameworks,
  programId,
  at,
}: {
  rows: RequirementRow[];
  frameworks: { id: string; name: string }[];
  programId: string;
  at?: string;
}) {
  const router = useRouter();
  const { pathname, search } = useListLocation();
  const state = search.get("state") as RequirementState | null;
  const fw = search.get("framework");
  const q = at ? `?at=${at}` : "";

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const counts = useMemo(() => {
    const c = Object.fromEntries(REQUIREMENT_STATES.map((s) => [s, 0])) as Record<RequirementState, number>;
    for (const r of rows) if (!fw || r.frameworkId === fw) c[r.state]++;
    return c;
  }, [rows, fw]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (!state || r.state === state) && (!fw || r.frameworkId === fw))
        .sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.displayId.localeCompare(b.displayId, undefined, { numeric: true })),
    [rows, state, fw],
  );

  const columns: DataTableColumn<RequirementRow>[] = useMemo(
    () => [
      {
        id: "displayId",
        header: "Requirement",
        width: 112,
        sortable: true,
        cell: (r) => <span className="font-mono text-xs">{r.displayId}</span>,
      },
      {
        id: "name",
        header: "Title",
        sortable: true,
        cell: (r) => (
          <span className="block min-w-0">
            <span className="block truncate">{r.name}</span>
            <span className="block truncate text-xs text-muted-foreground">{r.frameworkName}</span>
          </span>
        ),
      },
      {
        id: "state",
        header: "Coverage",
        width: 140,
        sortable: true,
        value: (r) => ORDER[r.state],
        cell: (r) => <RequirementStateBadge state={r.state} />,
      },
      {
        id: "controls",
        header: "Mapped controls",
        width: 220,
        hideBelow: "lg",
        value: (r) => r.controls.map((c) => c.displayId).join(" "),
        cell: (r) =>
          r.controls.length ? (
            <span className="flex flex-wrap gap-1">
              {r.controls.map((c) => (
                <Link
                  key={c.id}
                  href={`/programs/${programId}/controls/${c.id}${q}`}
                  className="rounded border bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] hover:border-foreground/40"
                >
                  {c.displayId}
                </Link>
              ))}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">No reviewed mapping</span>
          ),
      },
    ],
    [programId, q],
  );

  return (
    <DataTable
      data={visible}
      columns={columns}
      rowId={(r) => r.id}
      rowLabel={(r) => `${r.displayId} ${r.name}`}
      caption="Framework requirements in scope with their computed coverage state"
      searchable
      searchPlaceholder="Search requirements"
      searchText={(r) => `${r.displayId} ${r.name} ${r.frameworkName} ${r.id} ${r.controls.map((c) => c.displayId).join(" ")}`}
      clipboard={false}
      emptyState={<span className="text-sm text-muted-foreground">No requirements match these filters.</span>}
      toolbar={
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!state} onClick={() => setParam("state", null)}>
            All {Object.values(counts).reduce((a, b) => a + b, 0)}
          </Chip>
          {REQUIREMENT_STATES.map((s) => (
            <Chip key={s} active={state === s} onClick={() => setParam("state", state === s ? null : s)}>
              {s} {counts[s]}
            </Chip>
          ))}
          {frameworks.length > 1 && (
            <select
              aria-label="Framework"
              value={fw ?? ""}
              onChange={(e) => setParam("framework", e.target.value || null)}
              className="h-7 rounded-full border bg-transparent px-2.5 text-xs text-muted-foreground"
            >
              <option value="">All frameworks</option>
              {frameworks.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          )}
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
