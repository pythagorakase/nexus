/** Repository defaults plus separately persisted player preferences. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import type { Preferences, SettingsPatch, SettingsPayload, StorySettings } from "@/types/settings";

export const SETTINGS_QUERY_KEY = ["/api/settings"] as const;
export const PREFERENCES_QUERY_KEY = ["/api/preferences"] as const;

export function useSettingsQuery() {
  const defaults = useQuery<SettingsPayload>({ queryKey: [...SETTINGS_QUERY_KEY] });
  const preferences = useQuery<Preferences>({ queryKey: [...PREFERENCES_QUERY_KEY] });
  return {
    ...defaults,
    error: defaults.error ?? preferences.error,
    data: defaults.data && preferences.data
      ? applySettingsPatch(defaults.data, preferences.data)
      : defaults.data,
  };
}

/** Project player preferences onto the read-only display of defaults. */
export function applySettingsPatch(payload: SettingsPayload, patch: SettingsPatch): SettingsPayload {
  const fonts = { ...payload.ui?.fonts };
  for (const [theme, slots] of Object.entries(patch.fonts ?? {})) {
    const key = theme as keyof typeof fonts;
    fonts[key] = { ...fonts[key], ...slots } as NonNullable<typeof fonts[typeof key]>;
  }
  return {
    ...payload,
    ui: {
      ...payload.ui,
      ...(patch.theme === undefined ? {} : { theme: patch.theme }),
      ...(patch.fonts === undefined ? {} : { fonts: fonts as Preferences["fonts"] }),
    },
    wizard: {
      ...payload.wizard,
      ...(patch.wizard_model === undefined ? {} : { default_model: patch.wizard_model }),
    },
  };
}

export function useSettingsMutation() {
  const client = useQueryClient();
  return useMutation<Preferences, Error, SettingsPatch, { previous: Preferences | undefined }>({
    mutationFn: async (patch) => (await (await apiRequest("PATCH", "/api/preferences", patch)).json()),
    onMutate: async (patch) => {
      await client.cancelQueries({ queryKey: [...PREFERENCES_QUERY_KEY] });
      const previous = client.getQueryData<Preferences>(PREFERENCES_QUERY_KEY);
      if (previous) {
        const projected = applySettingsPatch({ ui: previous }, patch);
        client.setQueryData(PREFERENCES_QUERY_KEY, {
          ...previous, ...projected.ui,
          wizard_model: patch.wizard_model ?? previous.wizard_model,
        });
      }
      return { previous };
    },
    onError: (_error, _patch, context) => {
      if (context?.previous) client.setQueryData(PREFERENCES_QUERY_KEY, context.previous);
    },
    onSuccess: (preferences) => client.setQueryData(PREFERENCES_QUERY_KEY, preferences),
  });
}

export function useStorySettings(slot: number | null) {
  return useQuery<StorySettings>({
    queryKey: [`/api/slot/${slot}/settings`],
    enabled: slot !== null,
  });
}

export function useStorySettingsMutation(slot: number | null) {
  const client = useQueryClient();
  return useMutation<StorySettings, Error, Partial<StorySettings>>({
    mutationFn: async (patch) => {
      if (slot === null) throw new Error("No active slot");
      return (await (await apiRequest("PATCH", `/api/slot/${slot}/settings`, patch)).json());
    },
    onSuccess: (settings) => {
      client.setQueryData([`/api/slot/${slot}/settings`], settings);
      void client.invalidateQueries({ queryKey: [`/api/slot/${slot}/state`] });
    },
  });
}
