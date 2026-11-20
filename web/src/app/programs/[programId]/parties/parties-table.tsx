"use client";

import { useMemo, useState } from "react";
import { Building2, Shield, User, Users } from "lucide-react";
import { cn } from "cn";

import { RevokeButton } from "@/components/crud";
import { DataTable, type DataTableColumn } from "@/components/spectrumui/data-table";
import { StatusBadge } from "@/components/spectrumui/status-badge";
import { AgentMark } from "@/components/status";
import { revokeParty } from "@/lib/actions";
import type { Party } from "@/lib/api/types";

import { PartyCrudDialog } from "./party-crud";

export type PartyRow = {
  id: string;
  modified: string;
  name: string;
  kind: Party["kind"];
  isAgent: boolean;
  tags: string[];
  ownedControls: number;
  ownedRisks: number;
  ownedPolicies: number;
};

const KINDS: Party["kind"][] = ["person", "team", "role", "organization"];

function KindBadge({ kind }: { kind: Party["kind"] }) {
  if (kind === "person") return <StatusBadge tone="neutral" icon={User}>person</StatusBadge>;
  if (kind === "team") return <StatusBadge tone="contribution" icon={Users}>team</StatusBadge>;
  if (kind === "role") return <StatusBadge tone="waived" icon={Shield}>role</StatusBadge>;
  return <StatusBadge tone="neutral" icon={Building2}>organization</StatusBadge>;
}

export function PartiesTable({ rows }: { rows: PartyRow[] }) {
  const [kind, setKind] = useState<Party["kind"] | null>(null);

  const counts = useMemo(() => {
    const c: Record<Party["kind"], number> = { person: 0, team: 0, role: 0, organization: 0 };
    for (const r of rows) c[r.kind]++;
    return c;
  }, [rows]);

  const visible = useMemo(
    () =>
      rows
        .filter((r) => !kind || r.kind === kind)
        .sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind) || a.name.localeCompare(b.name)),
    [rows, kind],
  );

  const columns: DataTableColumn<PartyRow>[] = useMemo(
    () => [
      {
        id: "name",
        header: "Party",
        sortable: true,
        cell: (r) => (
          <div className="flex items-center gap-2">
            <span className="font-medium">{r.name}</span>
            {r.isAgent && <AgentMark label="Automated agent party" />}
          </div>
        ),
      },
      {
        id: "kind",
        header: "Kind",
        width: 132,
        sortable: true,
        cell: (r) => <KindBadge kind={r.kind} />,
      },
      {
        id: "ownedControls",
        header: "Controls",
        width: 92,
        sortable: true,
        cell: (r) => <span className="font-mono text-xs tabular-nums text-muted-foreground">{r.ownedControls}</span>,
      },
      {
        id: "ownedRisks",
        header: "Risks",
        width: 80,
        sortable: true,
        cell: (r) => <span className="font-mono text-xs tabular-nums text-muted-foreground">{r.ownedRisks}</span>,
      },
      {
        id: "ownedPolicies",
        header: "Policies",
        width: 88,
        sortable: true,
        cell: (r) => <span className="font-mono text-xs tabular-nums text-muted-foreground">{r.ownedPolicies}</span>,
      },
      {
        id: "id",
        header: "ID",
        width: 168,
        hideBelow: "lg",
        cell: (r) => <span className="font-mono text-xs text-muted-foreground">{r.id}</span>,
      },
      {
        id: "actions",
        header: "",
        width: 76,
        cell: (r) => (
          <div className="flex items-center justify-end gap-1">
            <PartyCrudDialog existing={r} />
            <RevokeButton compact label={`Revoke ${r.name}`} onRevoke={() => revokeParty(r.id, r.modified)} />
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <DataTable
      data={visible}
      columns={columns}
      rowId={(r) => r.id}
      rowLabel={(r) => r.name}
      caption="Organization parties, roles, agents, and subservice providers with ownership counts"
      searchable
      searchPlaceholder="Search parties"
      searchText={(r) => `${r.name} ${r.kind} ${r.id} ${r.tags.join(" ")}`}
      clipboard={false}
      emptyState={<span className="text-sm text-muted-foreground">No parties match this filter.</span>}
      toolbar={
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip active={!kind} onClick={() => setKind(null)}>
            All {rows.length}
          </Chip>
          {KINDS.map((k) => (
            <Chip key={k} active={kind === k} onClick={() => setKind(kind === k ? null : k)}>
              {k} {counts[k]}
            </Chip>
          ))}
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
