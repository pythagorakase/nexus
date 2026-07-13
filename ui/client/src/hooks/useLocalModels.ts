/**
 * Local-model manager state and actions (/api/local-models).
 *
 * Reads are React Query polls whose cadence the caller sets from the
 * `[ui.local_models]` knobs (activation swaps and downloads are watched
 * fast, rest state slow). Writes follow the useSecrets idiom: imperative
 * callbacks around apiRequest that invalidate both query keys so every
 * observer — the settings card and the topbar meter — converges on the
 * next poll.
 */
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Query } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import type {
  LocalDownloadStatus,
  LocalModelsStatus,
} from "@/types/localModels";

type PollInterval<T> =
  | number
  | false
  | ((query: Query<T, Error>) => number | false | undefined);

export const LOCAL_MODELS_STATUS_KEY = ["/api/local-models/status"] as const;
export const LOCAL_MODELS_DOWNLOAD_KEY = ["/api/local-models/download"] as const;

// Fallbacks used only until GET /api/settings resolves. Must stay in sync
// with `[ui.local_models]` in nexus.toml (UILocalModelsSettings defaults).
export const LOCAL_MODELS_KNOB_DEFAULTS = {
  poll_busy_ms: 1500,
  poll_idle_ms: 15_000,
  download_poll_ms: 1000,
  delete_arm_ms: 2800,
} as const;

// refetchIntervalInBackground: React Query pauses intervals while the
// document is hidden by default. A hidden window with a frozen memory
// meter or download bar reads as current the moment it is glanced at —
// keep polling; the endpoint is local and answers in milliseconds.
export function useLocalModelsStatus(pollMs: PollInterval<LocalModelsStatus>) {
  return useQuery<LocalModelsStatus>({
    queryKey: [...LOCAL_MODELS_STATUS_KEY],
    refetchInterval: pollMs,
    refetchIntervalInBackground: true,
  });
}

export function useLocalDownloadStatus(
  pollMs: PollInterval<LocalDownloadStatus>,
) {
  return useQuery<LocalDownloadStatus>({
    queryKey: [...LOCAL_MODELS_DOWNLOAD_KEY],
    refetchInterval: pollMs,
    refetchIntervalInBackground: true,
  });
}

export function useLocalModelActions() {
  const queryClient = useQueryClient();

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: [...LOCAL_MODELS_STATUS_KEY],
    });
    void queryClient.invalidateQueries({
      queryKey: [...LOCAL_MODELS_DOWNLOAD_KEY],
    });
  }, [queryClient]);

  const activate = useCallback(
    async (path: string) => {
      try {
        await apiRequest("POST", "/api/local-models/activate", { path });
      } finally {
        refresh();
      }
    },
    [refresh],
  );

  const deactivate = useCallback(async () => {
    try {
      await apiRequest("POST", "/api/local-models/deactivate");
    } finally {
      refresh();
    }
  }, [refresh]);

  const startDownload = useCallback(
    async (family: string, quant: string) => {
      try {
        await apiRequest("POST", "/api/local-models/download", {
          family,
          quant,
        });
      } finally {
        refresh();
      }
    },
    [refresh],
  );

  const cancelDownload = useCallback(async () => {
    try {
      await apiRequest("POST", "/api/local-models/download/cancel");
    } finally {
      refresh();
    }
  }, [refresh]);

  const deleteModel = useCallback(
    async (path: string) => {
      try {
        await apiRequest("POST", "/api/local-models/delete", { path });
      } finally {
        refresh();
      }
    },
    [refresh],
  );

  return { activate, deactivate, startDownload, cancelDownload, deleteModel };
}
