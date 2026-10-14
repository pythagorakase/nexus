/**
 * Shapes for the read-only GET /api/settings surface. The server types the
 * response as `SettingsPayload` in `nexus/api/settings_endpoints.py`: every
 * nexus.toml section except `secrets`, with concrete model selections, plus
 * the derived `settings_meta` block. This type declares only the fields the
 * client reads. Single source of truth for the client - extend here, not
 * locally.
 */

export type ThemeId = "veil" | "gilded" | "vector";
export type FontSlotId = "body" | "menu" | "display";

export interface FontSlots {
  body: string;
  menu: string;
  display: string;
}

export type FontMatrix = Record<ThemeId, FontSlots>;

/** One selectable model from [global.model.api_models]. */
export interface ModelOption {
  id: string;
  provider: string;
  label: string;
}

/** Derived metadata so the client never hardcodes config semantics. */
export interface SettingsMeta {
  models: ModelOption[];
  /** Providers APEXSettings.provider accepts (the wizard accepts all). */
  apex_allowed_providers: string[];
}

export interface LoreBudgetSlider {
  min: number;
  max: number;
  step: number;
  stops: number[];
}

/** Mirrors `[ui.local_models]` (UILocalModelsSettings in settings_models.py). */
export interface LocalModelsUiKnobs {
  poll_busy_ms?: number;
  poll_idle_ms?: number;
  download_poll_ms?: number;
  delete_arm_ms?: number;
}

/** Mirrors `[orrery.dashboard]` (OrreryDashboardSettings). */
export interface OrreryDashboardKnobs {
  backstage_poll_busy_ms?: number;
  backstage_poll_idle_ms?: number;
}

export interface SettingsPayload {
  /** Concrete model ID supplied by the roster. */
  apex?: { model?: string; gaia_model?: string | null };
  local_models?: { model?: string };
  lore?: {
    token_budget?: {
      apex_context_window?: number;
    };
  };
  orrery?: {
    dashboard?: OrreryDashboardKnobs;
  };
  /** Mirrors `[ui]` in nexus.toml (UISettings in settings_models.py). */
  ui?: {
    theme?: ThemeId;
    fonts?: FontMatrix;
    lore_budget_slider?: LoreBudgetSlider;
    local_models?: LocalModelsUiKnobs;
  };
  settings_meta?: SettingsMeta;
}

/** Player settings written only to the runtime preferences file. */
export interface Preferences {
  theme: ThemeId;
  fonts: FontMatrix;
  wizard_model: string;
}

export interface SettingsPatch {
  theme?: ThemeId;
  fonts?: Partial<Record<ThemeId, Partial<FontSlots>>>;
}

/** Null pins inherit defaults; null Gaia follows this story's Skald. */
export interface StorySettings {
  skald_model: string | null;
  gaia_model: string | null;
  apex_context_window: number | null;
}
