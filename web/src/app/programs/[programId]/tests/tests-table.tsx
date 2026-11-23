"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CircleCheck, CircleDashed, CircleX, AlertCircle } from "lucide-react";
import { cn } from "cn";

import { RecordManualResultButton } from "@/app/programs/[programId]/controls/[controlId]/control-crud";
import { RunTestButton } from "@/app/programs/[programId]/controls/[controlId]/run-test-button";
import { RevokeButton } from "@/components/crud";
import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { revokeTest } from "@/lib/actions";
import { isoDate } from "@/lib/format";

import { TestCrudDialog, type ControlOption } from "./test-crud";

export type TestStatus = "fail" | "error" | "missing" | "pass";

export type TestRow = {
  id: string;
  modified: string;
  name: string;
  controlId: string;
  controlDisplayId: string;
  implementationId?: string;
  method: "automated" | "manual";
  interval?: string;
  required?: boolean;
  command?: string;
  hasRun: boolean;
  status: TestStatus;
  observed?: string;
  summary?: string;
};

const ORDER: Record<TestStatus, number> = { fail: 0, error: 1, missing: 2, pass: 3 };
const STATUS_LIST: TestStatus[] = ["fail", "error", "missing", "pass"];

function TestOutcomeBadge({ status }: { status: TestStatus }) {
  if (status === "pass") return <StatusBadge tone="met" icon={CircleCheck}>pass</StatusBadge>;
  if (status === "fail") return <StatusBadge tone="gap" icon={CircleX}>fail</StatusBadge>;
  if (status === "error") return <StatusBadge tone="gap" icon={AlertCircle}>error</StatusBadge>;
  return <StatusBadge tone="waived" icon={CircleDashed}>no methodology</StatusBadge>;
}

export function TestsTable({
  rows,
  controls,
  programId,
  at,
}: {
  rows: TestRow[];
  controls: ControlOption[];
  programId: string;
  at?: string;
}) {
  const [filter, setFilter] = useState<TestStatus | null>(null);
  const [method, setMethod] = useState<string>("");
  const q = at ? `?at=${at}` : "";

  const counts = useMemo(() => {
    const c: Record<TestStatus, number> = { fail: 0, error: 0, missing: 0, pass: 0 };
    for (const r of rows) c[r.status]++;
    return c;
  }, [rows]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (!filter || r.status === filter) && (!method || r.method === method))
        .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.controlDisplayId.localeCompare(b.controlDisplayId)),
    [rows, filter, method],
  );

  const columns: DataTableColumn<TestRow>[] = useMemo(
    () => [
      {
        id: "controlDisplayId",
        header: "Control",
        width: 88,
        sortable: true,
        cell: (r) => (
          <Link
            href={`/programs/${programId}/controls/${r.controlId}${q}`}
            className="font-mono text-xs hover:underline"
          >
            {r.controlDisplayId}
          </Link>
        ),
      },
      {
        id: "name",
        header: "Test",
        sortable: true,
        cell: (r) => (
          <span className="block min-w-0">
            <span className="block truncate">{r.name}</span>
            {r.summary && <span className="block truncate text-xs text-gap-ink">{r.summary}</span>}
          </span>
        ),
      },
      {
        id: "status",
        header: "Outcome",
        width: 148,
        sortable: true,
        value: (r) => ORDER[r.status],
        cell: (r) => <TestOutcomeBadge status={r.status} />,
      },
      {
        id: "method",
        header: "Method",
        width: 132,
        hideBelow: "lg",
        sortable: true,
        cell: (r) => (
          <span className="text-xs text-muted-foreground">
            {r.method}
            {r.interval ? ` · ${r.interval}` : ""}
          </span>
        ),
      },
      {
        id: "observed",
        header: "Observed",
        width: 112,
        hideBelow: "lg",
        sortable: true,
        cell: (r) => <span className="text-xs text-muted-foreground tabular-nums">{isoDate(r.observed)}</span>,
      },
      {
        id: "action",
        header: "",
        width: 152,
        cell: (r) => (
          <div className="flex items-center justify-end gap-1">
            {r.hasRun && r.implementationId ? (
              <RunTestButton testId={r.id} implementationId={r.implementationId} />
            ) : r.method === "manual" && r.implementationId ? (
              <RecordManualResultButton testId={r.id} testName={r.name} implementationId={r.implementationId} />
            ) : null}
            <TestCrudDialog controls={controls} existing={r} />
            <RevokeButton compact label={`Revoke ${r.name}`} onRevoke={() => revokeTest(r.id, r.modified)} />
          </div>
        ),
      },
    ],
    [controls, programId, q],
  );

  return (
    <DataTable
      data={visible}
      columns={columns}
      rowId={(r) => r.id}
      rowLabel={(r) => `${r.controlDisplayId} ${r.name}`}
      caption="Required tests for baseline controls with latest result and run trigger"
      searchable
      searchPlaceholder="Search tests"
      searchText={(r) => `${r.controlDisplayId} ${r.name} ${r.method} ${r.summary ?? ""} ${r.id}`}
      clipboard={false}
      emptyState={<span className="text-sm text-muted-foreground">No tests match these filters.</span>}
      toolbar={
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!filter} onClick={() => setFilter(null)}>
            All {rows.length}
          </Chip>
          {STATUS_LIST.map((s) => (
            <Chip key={s} active={filter === s} onClick={() => setFilter(filter === s ? null : s)}>
              {s === "missing" ? "no methodology" : s} {counts[s]}
            </Chip>
          ))}
          <select
            aria-label="Method"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="h-7 rounded-full border bg-transparent px-2.5 text-xs text-muted-foreground"
          >
            <option value="">All methods</option>
            <option value="automated">automated</option>
            <option value="manual">manual</option>
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
