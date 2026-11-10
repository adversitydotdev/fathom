/**
 * The mock's stand-in for the kernel's computed views. Control state is
 * canned in the fixtures. Requirement coverage is derived from the fixture
 * mappings with a simplified version of RFC 0001 section 8 (no parts, no
 * combined sets) so the numbers stay consistent with the mapping data.
 *
 * This file exists only for fixtures. The web application never computes status.
 */
import type {
  ControlStatus,
  Gap,
  ProgramStatus,
  ProgramSummary,
  RequirementCoverage,
} from "@/lib/api/types";

import { db } from "./db";

const PATH_RELATIONSHIPS = new Set(["equal-to", "equivalent-to", "superset-of"]);

function evaluationTime(at: string | null): string {
  return at ?? db.now;
}

function within(date: string | undefined, from: string, days: number): boolean {
  if (!date) return false;
  const d = Date.parse(date.length === 10 ? `${date}T23:59:59Z` : date);
  const start = Date.parse(from);
  return d >= start && d <= start + days * 86_400_000;
}

export function programStatus(programId: string, at: string | null, frameworkId: string | null): ProgramStatus | undefined {
  const program = db.programs.find((p) => p.id === programId);
  const baseline = program && db.baselines.find((b) => b.id === program.baseline_ref);
  if (!program || !baseline) return undefined;

  const controlRefs = baseline.control_refs ?? [];
  const controls: ControlStatus[] = controlRefs.map((control_id) => {
    const s = db.controlStates.get(control_id);
    return s
      ? { control_id, state: s.state, implementation_id: s.implementation_id, failed: s.failed }
      : { control_id, state: "gap", failed: ["No implementation for this system"] };
  });
  const stateOf = new Map(controls.map((c) => [c.control_id, c.state]));

  const frameworks = frameworkId ? [frameworkId] : (baseline.framework_refs ?? []);
  const inScope = baseline.requirement_refs
    ? db.requirements.filter((r) => baseline.requirement_refs!.includes(r.id))
    : db.requirements.filter((r) => frameworks.includes(r.framework_ref) && !r.withdrawn && !r.revoked);

  const requirements: RequirementCoverage[] = inScope.map((r) => {
    const counted = db.mappings.filter(
      (m) =>
        m.target_ref.split("#")[0] === r.id &&
        controlRefs.includes(m.source_ref) &&
        m.review_status === "reviewed" &&
        m.relationship !== "no-relationship" &&
        !m.revoked,
    );
    const mapping_ids = counted.map((m) => m.id);
    if (counted.length === 0) return { requirement_id: r.id, state: "unmapped" };
    const paths = counted.filter((m) => PATH_RELATIONSHIPS.has(m.relationship));
    if (paths.length === 0) return { requirement_id: r.id, state: "contribution", mapping_ids };
    const holds = paths.some((m) => stateOf.get(m.source_ref) === "met");
    return { requirement_id: r.id, state: holds ? "covered" : "gap", mapping_ids };
  });

  return { program_id: programId, at: evaluationTime(at), controls, requirements };
}

export function programSummary(programId: string, at: string | null): ProgramSummary | undefined {
  const status = programStatus(programId, at, null);
  const program = db.programs.find((p) => p.id === programId);
  if (!status || !program) return undefined;
  const t = status.at;

  const count = <K extends string>(states: K[], keys: readonly K[]) =>
    Object.fromEntries(keys.map((k) => [k, states.filter((s) => s === k).length])) as Record<K, number>;

  const implIds = new Set(
    db.implementations.filter((i) => i.system_ref === program.system_ref).map((i) => i.id),
  );
  const latest = new Map<string, (typeof db.results)[number]>();
  for (const r of db.results) {
    const key = `${r.test_ref}|${r.implementation_ref}`;
    const prev = latest.get(key);
    if (!prev || prev.observed < r.observed) latest.set(key, r);
  }

  return {
    program_id: programId,
    at: t,
    controls: count(status.controls.map((c) => c.state), ["met", "gap", "waived", "out_of_scope"] as const),
    requirements: count(status.requirements.map((r) => r.state), ["covered", "contribution", "unmapped", "gap"] as const),
    failing_tests: [...latest.values()].filter((r) => implIds.has(r.implementation_ref) && r.outcome !== "pass").length,
    open_risks: db.risks.filter((r) => r.system_ref === program.system_ref && (r.status === "open" || r.status === "treating")).length,
    expiring_evidence: db.evidence.filter((e) => e.implementation_ref && implIds.has(e.implementation_ref) && within(e.valid_until, t, 30)).length,
    expiring_exceptions: db.exceptions.filter((e) => implIds.has(e.implementation_ref) && within(e.expires, t, 30)).length,
    open_findings: db.findings.filter((f) => f.system_ref === program.system_ref && f.determination === "not-satisfied").length,
  };
}

export function systemGaps(systemId: string, at: string | null): { at: string; gaps: Gap[] } {
  const gaps = db.programs
    .filter((p) => p.system_ref === systemId)
    .flatMap((p) =>
      (programStatus(p.id, at, null)?.controls ?? [])
        .filter((c) => c.state === "gap")
        .map((c) => ({ program_id: p.id, control_id: c.control_id, implementation_id: c.implementation_id, failed: c.failed ?? [] })),
    );
  return { at: evaluationTime(at), gaps };
}
