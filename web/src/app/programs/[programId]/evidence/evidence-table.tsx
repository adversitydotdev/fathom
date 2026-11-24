"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { FileCheck, FileUp, Link2, Terminal } from "lucide-react";
import { cn } from "cn";

import { RevokeButton } from "@/components/crud";
import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { revokeEvidence } from "@/lib/actions";
import type { Evidence } from "@/lib/api/types";
import { isoDate } from "@/lib/format";

import { EvidenceCrudDialog, type ImplOption } from "./evidence-crud";

export type ValidityState = "expired" | "expiring" | "valid";

export type EvidenceRow = {
  id: string;
  modified: string;
  name: string;
  method: Evidence["method"];
  implementationId?: string;
  controlId?: string;
  controlDisplayId?: string;
  collected: string;
  validUntil?: string;
  validity: ValidityState;
  digestShort?: string;
  mediaType?: string;
  uri?: string;
};

const ORDER: Record<ValidityState, number> = { expired: 0, expiring: 1, valid: 2 };

function MethodIcon({ method }: { method: Evidence["method"] }) {
  const Icon = { automated: Terminal, upload: FileUp, attestation: FileCheck, link: Link2 }[method];
  return <Icon className="size-3.5 text-muted-foreground" aria-hidden />;
}

export function EvidenceTable({
  rows,
  implementations,
  programId,
  at,
}: {
  rows: EvidenceRow[];
  implementations: ImplOption[];
  programId: string;
  at?: string;
}) {
  const [validity, setValidity] = useState<ValidityState | null>(null);
  const [method, setMethod] = useState<string>("");
  const q = at ? `?at=${at}` : "";

  const counts = useMemo(() => {
    const c: Record<ValidityState, number> = { expired: 0, expiring: 0, valid: 0 };
    for (const r of rows) c[r.validity]++;
    return c;
  }, [rows]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => (!validity || r.validity === validity) && (!method || r.method === method))
        .sort((a, b) => ORDER[a.validity] - ORDER[b.validity] || a.name.localeCompare(b.name)),
    [rows, validity, method],
  );

  const columns: DataTableColumn<EvidenceRow>[] = useMemo(
    () => [
      {
        id: "name",
        header: "Artifact",
        sortable: true,
        cell: (r) => (
          <span className="flex items-center gap-2 min-w-0">
            <MethodIcon method={r.method} />
            <span className="min-w-0">
              <span className="block truncate">{r.name}</span>
              <span className="block truncate font-mono text-[11px] text-muted-foreground">
                {r.method}
                {r.digestShort ? ` · sha256:${r.digestShort}` : ""}
              </span>
            </span>
          </span>
        ),
      },
      {
        id: "controlDisplayId",
        header: "Control",
        width: 96,
        sortable: true,
        cell: (r) =>
          r.controlId ? (
            <Link
              href={`/programs/${programId}/controls/${r.controlId}${q}`}
              className="font-mono text-xs hover:underline"
            >
              {r.controlDisplayId}
            </Link>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: "collected",
        header: "Collected",
        width: 112,
        hideBelow: "lg",
        sortable: true,
        cell: (r) => <span className="text-xs text-muted-foreground tabular-nums">{isoDate(r.collected)}</span>,
      },
      {
        id: "validUntil",
        header: "Valid until",
        width: 128,
        sortable: true,
        value: (r) => ORDER[r.validity],
        cell: (r) => {
          const tone = r.validity === "expired" ? "gap" : r.validity === "expiring" ? "waived" : "met";
          return <StatusBadge tone={tone}>{r.validUntil ? isoDate(r.validUntil) : "open"}</StatusBadge>;
        },
      },
      {
        id: "actions",
        header: "",
        width: 84,
        cell: (r) => (
          <div className="flex items-center justify-end gap-1">
            <EvidenceCrudDialog implementations={implementations} existing={r} />
            <RevokeButton compact label={`Revoke ${r.name}`} onRevoke={() => revokeEvidence(r.id, r.modified)} />
          </div>
        ),
      },
    ],
    [implementations, programId, q],
  );

  return (
    <DataTable
      data={visible}
      density="compact"
      stickyHeader
      maxHeight="max(24rem, calc(100dvh - 17rem))"
      columns={columns}
      rowId={(r) => r.id}
      rowLabel={(r) => r.name}
      caption="Evidence records attached to implementations and test results"
      searchable
      searchPlaceholder="Search evidence"
      searchText={(r) => `${r.name} ${r.controlDisplayId ?? ""} ${r.method} ${r.id}`}
      clipboard={false}
      emptyState={<span className="text-sm text-muted-foreground">No evidence matches these filters.</span>}
      toolbar={
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!validity} onClick={() => setValidity(null)}>
            All {rows.length}
          </Chip>
          <Chip active={validity === "expired"} onClick={() => setValidity(validity === "expired" ? null : "expired")}>
            expired {counts.expired}
          </Chip>
          <Chip active={validity === "expiring"} onClick={() => setValidity(validity === "expiring" ? null : "expiring")}>
            expiring ≤30d {counts.expiring}
          </Chip>
          <Chip active={validity === "valid"} onClick={() => setValidity(validity === "valid" ? null : "valid")}>
            valid {counts.valid}
          </Chip>
          <select
            aria-label="Evidence method"
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="h-7 rounded-full border bg-transparent px-2.5 text-xs text-muted-foreground"
          >
            <option value="">All methods</option>
            <option value="automated">automated</option>
            <option value="upload">upload</option>
            <option value="attestation">attestation</option>
            <option value="link">link</option>
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
