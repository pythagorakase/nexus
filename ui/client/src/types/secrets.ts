/** Browser-safe wire contracts for the `/api/secrets` surface. */

export interface SecretStatus {
  provider: string;
  account: string;
  present: boolean;
  last4: string | null;
}

export interface SecretVerification {
  provider: string;
  verified: boolean;
  detail: string;
}
