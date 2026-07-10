/**
 * API key status and actions. Only masked status rows enter React Query;
 * plaintext keys pass directly from component draft state to `fetch` and are
 * never retained as query or mutation state.
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import type { SecretStatus, SecretVerification } from "@/types/secrets";

export const SECRETS_QUERY_KEY = ["/api/secrets/status"] as const;

export function useSecretsQuery() {
  return useQuery<SecretStatus[]>({ queryKey: [...SECRETS_QUERY_KEY] });
}

export function useSetSecret() {
  const queryClient = useQueryClient();

  return useCallback(
    async (provider: string, key: string): Promise<SecretStatus> => {
      const encodedProvider = encodeURIComponent(provider);
      const response = await apiRequest("PUT", `/api/secrets/${encodedProvider}`, {
        key,
      });
      const status = (await response.json()) as SecretStatus;
      queryClient.setQueryData<SecretStatus[]>(
        [...SECRETS_QUERY_KEY],
        (current = []) => {
          const next = current.filter((row) => row.provider !== status.provider);
          const index = current.findIndex((row) => row.provider === status.provider);
          next.splice(index < 0 ? next.length : index, 0, status);
          return next;
        },
      );
      return status;
    },
    [queryClient],
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
