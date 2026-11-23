"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, ShieldAlert } from "lucide-react";
import { cn } from "cn";

import { RevokeButton } from "@/components/crud";
import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { revokeRisk } from "@/lib/actions";
import type { Risk } from "@/lib/api/types";
import { isoDate } from "@/lib/format";

import { RiskCrudDialog, type Option } from "./risk-crud";

export type RiskRow = {
  id: string;
  modified: string;
  name: string;
  statement: string;
  likelihood: number;
  impact: number;
  residualLikelihood?: number;
  residualImpact?: number;
  treatment?: Risk["treatment"];
  status: Risk["status"];
  ownerId?: string;
  owner: string;
  controls: { id: string; displayId: string }[];
  milestones: { name: string; due?: string; completed?: string }[];
};

const LIKELIHOOD_LABELS = ["Rare", "Unlikely", "Possible", "Likely", "Almost certain"];
const IMPACT_LABELS = ["Negligible", "Minor", "Moderate", "Major", "Severe"];
const STATUS_ORDER: Record<Risk["status"], number> = { open: 0, treating: 1, accepted: 2, closed: 3 };
const STATUS_LIST: Risk["status"][] = ["open", "treating", "accepted", "closed"];

function RiskStatusBadge({ status }: { status: Risk["status"] }) {
  if (status === "open") return <StatusBadge tone="gap" icon={ShieldAlert}>open</StatusBadge>;
  if (status === "treating") return <StatusBadge tone="waived" icon={Clock}>treating</StatusBadge>;
  if (status === "accepted") return <StatusBadge tone="contribution" icon={AlertTriangle}>accepted</StatusBadge>;
  return <StatusBadge tone="met" icon={CheckCircle2}>closed</StatusBadge>;
}

function scoreTone(score: number): string {
  if (score >= 12) return "bg-gap-soft text-gap-ink border-gap/35";
  if (score >= 6) return "bg-waived-soft text-waived-ink border-waived/40";
  if (score >= 3) return "bg-contribution-soft text-contribution-ink border-contribution/30";
  return "bg-met-soft text-met-ink border-met/30";
}

function matrixCellTone(score: number, hasItems: boolean): string {
  if (!hasItems) {
    if (score >= 12) return "bg-gap-soft/30 border-border/60 text-muted-foreground/40";
    if (score >= 6) return "bg-waived-soft/25 border-border/60 text-muted-foreground/40";
    return "bg-muted/20 border-border/60 text-muted-foreground/40";
  }
  if (score >= 12) return "bg-gap-soft text-gap-ink border-gap/45 font-semibold";
  if (score >= 6) return "bg-waived-soft text-waived-ink border-waived/50 font-semibold";
  if (score >= 3) return "bg-contribution-soft text-contribution-ink border-contribution/40 font-semibold";
  return "bg-met-soft text-met-ink border-met/40 font-semibold";
}

export function RisksView({
  rows,
  systemId,
  parties,
  controls,
  programId,
  at,
}: {
  rows: RiskRow[];
  systemId: string;
  parties: Option[];
  controls: Option[];
  programId: string;
  at?: string;
}) {
  const [statusFilter, setStatusFilter] = useState<Risk["status"] | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ l: number; i: number } | null>(null);
  const [matrixMode, setMatrixMode] = useState<"inherent" | "residual">("inherent");
  const q = at ? `?at=${at}` : "";

  const counts = useMemo(() => {
    const c: Record<Risk["status"], number> = { open: 0, treating: 0, accepted: 0, closed: 0 };
    for (const r of rows) c[r.status]++;
    return c;
  }, [rows]);

  const cellCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const r of rows) {
      const l = matrixMode === "residual" ? (r.residualLikelihood ?? r.likelihood) : r.likelihood;
      const i = matrixMode === "residual" ? (r.residualImpact ?? r.impact) : r.impact;
      if (l >= 1 && l <= 5 && i >= 1 && i <= 5) {
        const key = `${l}-${i}`;
        map.set(key, (map.get(key) ?? 0) + 1);
      }
    }
    return map;
  }, [rows, matrixMode]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => {
          if (statusFilter && r.status !== statusFilter) return false;
          if (selectedCell) {
            const l = matrixMode === "residual" ? (r.residualLikelihood ?? r.likelihood) : r.likelihood;
            const i = matrixMode === "residual" ? (r.residualImpact ?? r.impact) : r.impact;
            return l === selectedCell.l && i === selectedCell.i;
          }
          return true;
        })
        .sort(
          (a, b) =>
            b.likelihood * b.impact - a.likelihood * a.impact ||
            STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
            a.name.localeCompare(b.name),
        ),
    [rows, statusFilter, selectedCell, matrixMode],
  );

  const columns: DataTableColumn<RiskRow>[] = useMemo(
    () => [
      {
        id: "name",
        header: "Risk",
        sortable: true,
        cell: (r) => (
          <div className="min-w-0 whitespace-normal py-0.5">
            <div className="font-medium">{r.name}</div>
            <p className="line-clamp-2 text-xs text-muted-foreground">{r.statement}</p>
            {r.milestones.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                {r.milestones.map((m) => (
                  <span key={m.name} className="rounded border bg-muted/30 px-1.5 py-0.5">
                    {m.name}
                    {m.due ? ` · due ${isoDate(m.due)}` : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        ),
      },
      {
        id: "score",
        header: "Score",
        width: 112,
        sortable: true,
        value: (r) => r.likelihood * r.impact,
        cell: (r) => {
          const score = r.likelihood * r.impact;
          const res =
            r.residualLikelihood && r.residualImpact ? r.residualLikelihood * r.residualImpact : undefined;
          return score > 0 ? (
            <div className="flex flex-col items-start gap-1">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-xs tabular-nums",
                  scoreTone(score),
                )}
                title={`Inherent: Likelihood ${r.likelihood} × Impact ${r.impact}`}
              >
                {score}
                <span className="opacity-70">({r.likelihood}×{r.impact})</span>
              </span>
              {res !== undefined && (
                <span className="text-xs tabular-nums text-muted-foreground">
                  residual {res} ({r.residualLikelihood}×{r.residualImpact})
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          );
        },
      },
      {
        id: "status",
        header: "Status",
        width: 112,
        sortable: true,
        value: (r) => STATUS_ORDER[r.status],
        cell: (r) => (
          <div className="flex flex-col items-start gap-1">
            <RiskStatusBadge status={r.status} />
            {r.treatment && <span className="text-xs text-muted-foreground capitalize">{r.treatment}</span>}
          </div>
        ),
      },
      {
        id: "owner",
        header: "Owner",
        width: 136,
        hideBelow: "lg",
        sortable: true,
        cell: (r) => <span className="text-xs text-muted-foreground">{r.owner}</span>,
      },
      {
        id: "controls",
        header: "Controls",
        width: 96,
        cell: (r) => (
          <div className="flex flex-wrap gap-1.5">
            {r.controls.length === 0 ? (
              <span className="text-xs text-muted-foreground">—</span>
            ) : (
              r.controls.map((c) => (
                <Link
                  key={c.id}
                  href={`/programs/${programId}/controls/${c.id}${q}`}
                  className="rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] hover:border-foreground/40 hover:text-foreground"
                >
                  {c.displayId}
                </Link>
              ))
            )}
          </div>
        ),
      },
      {
        id: "actions",
        header: "",
        width: 76,
        cell: (r) => (
          <div className="flex items-center justify-end gap-1">
            <RiskCrudDialog
              systemId={systemId}
              parties={parties}
              controls={controls}
              existing={{ ...r, controlIds: r.controls.map((c) => c.id) }}
            />
            <RevokeButton compact label={`Revoke ${r.name}`} onRevoke={() => revokeRisk(r.id, r.modified)} />
          </div>
        ),
      },
    ],
    [controls, parties, programId, q, systemId],
  );

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-xl border bg-card p-5" aria-label="Risk matrix">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold">Risk matrix</h2>
            <p className="text-xs text-muted-foreground">
              Likelihood (vertical) × Impact (horizontal). Click any cell to filter the register below.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <Chip active={matrixMode === "inherent"} onClick={() => setMatrixMode("inherent")}>
              Inherent
            </Chip>
            <Chip active={matrixMode === "residual"} onClick={() => setMatrixMode("residual")}>
              Residual
            </Chip>
            {selectedCell && (
              <button
                type="button"
                onClick={() => setSelectedCell(null)}
                className="h-7 rounded-full border border-foreground/30 px-2.5 text-xs text-foreground hover:bg-muted"
              >
                Clear cell ({selectedCell.l}×{selectedCell.i})
              </button>
            )}
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="grid min-w-[520px] grid-cols-[124px_repeat(5,minmax(0,1fr))] gap-1.5">
            {[5, 4, 3, 2, 1].map((l) => (
              <div key={l} className="contents">
                <div className="flex items-center justify-end pr-2 text-xs text-muted-foreground">
                  <span className="truncate">{LIKELIHOOD_LABELS[l - 1]}</span>
                  <span className="ml-1.5 opacity-60">{l}</span>
                </div>
                {[1, 2, 3, 4, 5].map((i) => {
                  const count = cellCounts.get(`${l}-${i}`) ?? 0;
                  const active = selectedCell?.l === l && selectedCell?.i === i;
                  return (
                    <button
                      key={`${l}-${i}`}
                      type="button"
                      onClick={() => setSelectedCell(active ? null : { l, i })}
                      aria-pressed={active}
                      aria-label={`Likelihood ${l} (${LIKELIHOOD_LABELS[l - 1]}), Impact ${i} (${IMPACT_LABELS[i - 1]}): ${count} risks`}
                      className={cn(
                        "flex h-11 items-center justify-center rounded-lg border text-xs font-medium tabular-nums transition-all",
                        matrixCellTone(l * i, count > 0),
                        active && "ring-2 ring-foreground ring-offset-2 ring-offset-card",
                      )}
                    >
                      {count > 0 ? count : "·"}
                    </button>
                  );
                })}
              </div>
            ))}
            <div />
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="pt-1 text-center text-xs text-muted-foreground">
                <span>{IMPACT_LABELS[i - 1]}</span>
                <span className="ml-1 opacity-60">{i}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <DataTable
        data={visible}
        columns={columns}
        rowId={(r) => r.id}
        rowLabel={(r) => r.name}
        caption="Risk register with inherent and residual scores, treatment, owner, and linked controls"
        searchable
        searchPlaceholder="Search risks"
        searchText={(r) => `${r.name} ${r.statement} ${r.owner} ${r.treatment ?? ""} ${r.controls.map((c) => c.displayId).join(" ")}`}
        clipboard={false}
        emptyState={<span className="text-sm text-muted-foreground">No risks match these filters.</span>}
        toolbar={
          <div className="flex flex-wrap items-center gap-1.5">
            <Chip active={!statusFilter} onClick={() => setStatusFilter(null)}>
              All {rows.length}
            </Chip>
            {STATUS_LIST.map((s) => (
              <Chip key={s} active={statusFilter === s} onClick={() => setStatusFilter(statusFilter === s ? null : s)}>
                {s} {counts[s]}
              </Chip>
            ))}
          </div>
        }
      />
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
