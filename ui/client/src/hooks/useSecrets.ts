/**
 * API key status and actions. Only masked status rows enter React Query;
 * plaintext keys pass directly from component draft state to `fetch` and are
 * never retained as query or mutation state.
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import type { SecretStatus, SecretVerification } from "@/types/secrets";

/** Prefix of every status query; invalidating it refreshes every slot's rows. */
export const SECRETS_QUERY_KEY = ["/api/secrets/status"] as const;

/** Requiredness follows the slot's story pins, so each slot caches its own rows. */
export function secretsQueryKey(slot: number | null) {
  return [...SECRETS_QUERY_KEY, { slot }] as const;
}

function slotQuery(slot: number | null): string {
  return slot === null ? "" : `?slot=${slot}`;
}

export function useSecretsQuery(slot: number | null) {
  return useQuery<SecretStatus[]>({
    queryKey: secretsQueryKey(slot),
    queryFn: async () =>
      (await apiRequest("GET", `/api/secrets/status${slotQuery(slot)}`)).json(),
  });
}

export function useSetSecret(slot: number | null) {
  const queryClient = useQueryClient();

  return useCallback(
    async (provider: string, key: string): Promise<SecretStatus> => {
      const encodedProvider = encodeURIComponent(provider);
      const response = await apiRequest(
        "PUT",
        `/api/secrets/${encodedProvider}${slotQuery(slot)}`,
        { key },
      );
      const status = (await response.json()) as SecretStatus;
      queryClient.setQueryData<SecretStatus[]>(
        secretsQueryKey(slot),
        (current = []) => {
          const next = current.filter((row) => row.provider !== status.provider);
          const index = current.findIndex((row) => row.provider === status.provider);
          next.splice(index < 0 ? next.length : index, 0, status);
          return next;
        },
      );
      return status;
    },
    [queryClient, slot],
  );
}

export function useVerifySecret() {
  return useCallback(async (provider: string): Promise<SecretVerification> => {
    const encodedProvider = encodeURIComponent(provider);
    const response = await apiRequest(
      "POST",
      `/api/secrets/${encodedProvider}/verify`,
    );
    return (await response.json()) as SecretVerification;
  }, []);
}
