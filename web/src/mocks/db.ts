import * as f from "./fixtures/program";
import { requirements } from "./fixtures/requirements";

/**
 * In-memory store behind the mock handlers. Module state, so it lives as long
 * as the server process. Writes mutate it; restart the dev server to reset.
 */
export const db = {
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
  procedures: [...f.procedures],
  jobs: [...f.jobs],
  libraryPin: { ...f.libraryPin },
  providers: [...f.providers],
  controlStates: f.controlStates,
};
