/** Browser-safe wire contracts for the `/api/secrets` surface. */

/** Model seats whose resolved provider can make a key required. */
export type SecretSeat =
  | "skald"
  | "gaia"
  | "wizard"
  | "orrery.experiences.model"
  | "storyteller.correspondence.compaction_model"
  | "orrery.retrograde.maturation.model_ref"
  | "summaries.model";

export interface SecretRequirement {
  seat: SecretSeat;
  model: string;
}

export interface SecretStatus {
  provider: string;
  account: string;
  present: boolean;
  last4: string | null;
  required: boolean;
  required_by: SecretRequirement[];
}

export interface SecretVerification {
  provider: string;
  verified: boolean;
  detail: string;
}
