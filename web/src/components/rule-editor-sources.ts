import type { Integration } from "@/lib/api/types";

import type { RuleSource } from "./rule-editor";

export { RuleEditorDialog } from "./rule-editor";

/** Every resource and saved query source of every installed integration, as a source a rule can read. */
export function ruleSourcesOf(integrations: Integration[]): RuleSource[] {
  return integrations.flatMap((i) => [
    ...i.resources.map((r) => ({ source: r.source, integration: i.name, resource: r.name, fields: r.fields })),
    ...(i.queries ?? []).map((q) => ({
      source: q.source,
      integration: i.name,
      resource: `${q.name}@${q.version} (query)`,
      fields: q.fields,
    })),
  ]);
}
