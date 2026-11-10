import type { Party } from "./api/types";

/**
 * RFC 0003 section 4 records an agent as a `party` in `created_by_ref`, but the
 * contract does not yet say how a client tells an agent party from a person.
 * Until it does, an agent party carries the `agent` tag. Change it here only.
 */
export function isAgentParty(party: Party | undefined): boolean {
  return party?.tags?.includes("agent") ?? false;
}

export function createdByAgent(createdBy: string | undefined, parties: Map<string, Party>): boolean {
  return createdBy ? isAgentParty(parties.get(createdBy)) : false;
}
