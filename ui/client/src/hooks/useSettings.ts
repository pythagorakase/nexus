/**
 * Server-backed settings: GET /api/settings query + PATCH mutation with
 * optimistic cache updates, rollback on error, and server confirmation
 * (the PATCH response is the fresh payload and replaces the cache).
 *
 * All settings writes in the client flow through useSettingsMutation -
 * there is no local draft state anywhere in the settings surface.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import type {
  FontSlots,
  SettingsPatch,
  SettingsPayload,
  ThemeId,
} from "@/types/settings";

export const SETTINGS_QUERY_KEY = ["/api/settings"] as const;

export function useSettingsQuery() {
  return useQuery<SettingsPayload>({ queryKey: [...SETTINGS_QUERY_KEY] });
}

/** Pure optimistic projection of a patch onto the cached payload. */
export function applySettingsPatch(
  payload: SettingsPayload,
  patch: SettingsPatch,
): SettingsPayload {
  const next: SettingsPayload = {
    ...payload,
    ui: { ...payload.ui },
  };

  if (patch.theme !== undefined) {
    next.ui = { ...next.ui, theme: patch.theme };
  }
  if (patch.fonts !== undefined && payload.ui?.fonts) {
    const fonts = { ...payload.ui.fonts };
    for (const [themeId, slots] of Object.entries(patch.fonts) as Array<
      [ThemeId, Partial<FontSlots>]
    >) {
      fonts[themeId] = { ...fonts[themeId], ...slots };
    }
    next.ui = { ...next.ui, fonts };
  }
  if (patch.typewriter_ms_per_char !== undefined) {
    next.ui = { ...next.ui, typewriter_ms_per_char: patch.typewriter_ms_per_char };
  }
  if (patch.test_mode !== undefined) {
    next.global = {
      ...payload.global,
      narrative: { ...payload.global?.narrative, test_mode: patch.test_mode },
    };
    next["Agent Settings"] = {
      ...payload["Agent Settings"],
      global: {
        ...payload["Agent Settings"]?.global,
        narrative: {
          ...payload["Agent Settings"]?.global?.narrative,
          test_mode: patch.test_mode,
        },
      },
    };
  }
  if (patch.apex_model_ref !== undefined) {
    const provider = patch.apex_model_ref.replace(/^@/, "").split(".")[0];
    next.apex = { ...payload.apex, model: patch.apex_model_ref, provider };
  }
  if (patch.wizard_model_ref !== undefined) {
    next.wizard = { ...payload.wizard, default_model: patch.wizard_model_ref };
  }
  if (patch.apex_context_window !== undefined) {
    next.lore = {
      ...payload.lore,
      token_budget: {
        ...payload.lore?.token_budget,
        apex_context_window: patch.apex_context_window,
      },
    };
  }
  return next;
}

export function useSettingsMutation() {
  return useMutation<
    SettingsPayload,
    Error,
    SettingsPatch,
    { previous: SettingsPayload | undefined }
  >({
    mutationFn: async (patch: SettingsPatch) => {
      const res = await apiRequest("PATCH", "/api/settings", patch);
      return (await res.json()) as SettingsPayload;
    },
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: [...SETTINGS_QUERY_KEY] });
      const previous = queryClient.getQueryData<SettingsPayload>([
        ...SETTINGS_QUERY_KEY,
      ]);
      if (previous) {
        queryClient.setQueryData(
          [...SETTINGS_QUERY_KEY],
          applySettingsPatch(previous, patch),
        );
      }
      return { previous };
    },
    onError: (error, _patch, context) => {
      if (context?.previous) {
        queryClient.setQueryData([...SETTINGS_QUERY_KEY], context.previous);
      }
      console.error("Settings update failed:", error);
    },
    onSuccess: (serverPayload) => {
      // Server confirmation: the PATCH response is the authoritative state.
      queryClient.setQueryData([...SETTINGS_QUERY_KEY], serverPayload);
    },
  });
}
