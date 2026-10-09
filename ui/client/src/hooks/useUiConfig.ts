import { useQuery } from "@tanstack/react-query";

export const UI_CONFIG_KEY = ["/api/config/ui"] as const;

export interface UiConfig {
  announcer: { hold_ms: number };
}

/** Read allowlisted player display tunables; surface failures to ErrorBoundary. */
export function useUiConfig(): UiConfig | undefined {
  const { data, error } = useQuery<UiConfig>({
    queryKey: UI_CONFIG_KEY,
    queryFn: async ({ signal }) => {
      const response = await fetch("/api/config/ui", { signal });
      if (!response.ok) {
        throw new Error(`${response.status}: ${await response.text()}`);
      }
      return response.json();
    },
  });
  if (error) throw error;
  return data;
}
