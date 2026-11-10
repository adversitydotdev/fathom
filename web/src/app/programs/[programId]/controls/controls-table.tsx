"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { cn } from "cn";

import { AgentMark, CONTROL_STATES, ControlStateBadge, controlStateLabel } from "@/components/status";
import { Input } from "@/components/ui/input";
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

/** Gaps first, then the rest, each by display id. */
const ORDER: Record<ControlState, number> = { gap: 0, waived: 1, met: 2, out_of_scope: 3 };

export function ControlsTable({ rows, programId, at }: { rows: ControlRow[]; programId: string; at?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const state = search.get("state") as ControlState | null;
  const family = search.get("family");
  const q = search.get("q") ?? "";

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

  const visible = rows
    .filter((r) => !state || r.state === state)
    .filter((r) => !family || r.family === family)
    .filter((r) => !q || `${r.displayId} ${r.name} ${r.owner ?? ""} ${r.id}`.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.displayId.localeCompare(b.displayId));

  const detailHref = (id: string) => `/programs/${programId}/controls/${id}${at ? `?at=${at}` : ""}`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            defaultValue={q}
            placeholder="IAM-02, encryption, owner"
            aria-label="Search controls"
            className="h-8 w-60 pl-8 text-sm"
            onChange={(e) => setParam("q", e.target.value || null)}
          />
        </div>
        <Chip active={!state} onClick={() => setParam("state", null)}>
          All {rows.length}
        </Chip>
        {CONTROL_STATES.map((s) => (
          <Chip key={s} active={state === s} onClick={() => setParam("state", state === s ? null : s)}>
            {controlStateLabel(s)} {counts[s]}
          </Chip>
        ))}
        <div className="flex-1" />
        <select
          aria-label="Family"
          value={family ?? ""}
          onChange={(e) => setParam("family", e.target.value || null)}
          className="h-8 rounded-md border bg-transparent px-2 text-sm text-muted-foreground"
        >
          <option value="">All families</option>
          {families.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full min-w-[56rem] table-fixed text-sm">
          <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              <th className="w-20 px-3 py-2 font-normal">Id</th>
              <th className="px-3 py-2 font-normal">Control</th>
              <th className="w-24 px-3 py-2 font-normal">State</th>
              <th className="w-72 px-3 py-2 font-normal">Failed condition</th>
              <th className="w-28 px-3 py-2 font-normal">Implementation</th>
              <th className="w-36 px-3 py-2 font-normal">Owner</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {visible.map((r) => (
              <tr key={r.id} className="group cursor-pointer hover:bg-muted/50" onClick={() => router.push(detailHref(r.id))}>
                <td className="px-3 py-2.5 font-mono text-xs">{r.displayId}</td>
                <td className="truncate px-3 py-2.5">
                  <Link href={detailHref(r.id)} className="outline-none group-hover:underline focus-visible:underline" onClick={(e) => e.stopPropagation()}>
                    {r.name}
                  </Link>
                  {r.byAgent && <span className="ml-1.5 align-[-2px]"><AgentMark /></span>}
                  <span className="block truncate text-xs text-muted-foreground">{r.family}</span>
                </td>
                <td className="px-3 py-2.5">
                  <ControlStateBadge state={r.state} />
                </td>
                <td className="truncate px-3 py-2.5 text-xs text-gap-ink" title={r.failed.join("\n")}>
                  {r.failed[0] ?? <span className="text-muted-foreground">—</span>}
                  {r.failed.length > 1 && <span className="text-muted-foreground"> +{r.failed.length - 1}</span>}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{r.implStatus ?? "none"}</td>
                <td className="truncate px-3 py-2.5 text-muted-foreground">{r.owner ?? "—"}</td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-10 text-center text-sm text-muted-foreground">
                  No controls match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
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
