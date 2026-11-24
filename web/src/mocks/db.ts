import * as f from "./fixtures/program";
import { queryDefinitions } from "./fixtures/queries";
import { requirements } from "./fixtures/requirements";

function createDb() {
  return {
    now: f.FIXTURE_NOW,
    parties: [...f.parties],
    components: [...f.components],
    systems: [...f.systems],
    frameworks: [...f.frameworks],
    requirements: [...requirements],
    controls: [...f.controls],
    mappings: [...f.mappings],
    baselines: [...f.baselines],
    programs: [...f.programs],
    implementations: [...f.implementations],
    tests: [...f.tests],
    results: [...f.results],
    evidence: [...f.evidenceItems],
    exceptions: [...f.exceptions],
    findings: [...f.findings],
    risks: [...f.risks],
    policies: [...f.policies],
    bodies: { ...f.documentBodies } as Record<string, string>,
    procedures: [...f.procedures],
    jobs: [...f.jobs],
    libraryPin: { ...f.libraryPin },
    providers: [...f.providers],
    integrations: [...f.integrations],
    connections: [...f.connections],
    queries: [...queryDefinitions],
    snapshots: [...f.snapshots],
    integrationVersions: [...f.integrationVersions],
    templateUpdates: [...f.templateUpdates],
    controlStates: f.controlStates,
  };
}

type MockDb = ReturnType<typeof createDb>;

const g = globalThis as typeof globalThis & { __fathomMockDb?: MockDb };

/**
 * In-memory store behind the mock handlers, pinned to `globalThis` so route
 * handlers (`/api/agent/stream`, `/v1/*`) and Server Components share one
 * instance across Next.js bundle chunks.
 */
export const db: MockDb = (g.__fathomMockDb ??= createDb());
