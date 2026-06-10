/**
 * Shapes for the GET/PATCH /api/settings surface (FastAPI, proxied by
 * Express). GET serves raw nexus.toml (role references like
 * "@openai.default" left unresolved) plus legacy "Agent Settings" aliases
 * and a derived `settings_meta` block. Single source of truth for the
 * client - extend here, not locally.
 */

export type ThemeId = "veil" | "gilded" | "vector";
export type FontSlotId = "body" | "menu" | "display";

export interface FontSlots {
  body: string;
  menu: string;
  display: string;
}

export type FontMatrix = Record<ThemeId, FontSlots>;

/** One selectable @provider.role binding from [global.model.api_models]. */
export interface ModelRoleOption {
  ref: string;
  provider: string;
  role: string;
  model_id: string;
  label: string;
}

/** Derived metadata so the client never hardcodes config semantics. */
export interface SettingsMeta {
  model_roles: ModelRoleOption[];
  /** Providers APEXSettings.provider accepts (the wizard accepts all). */
  apex_allowed_providers: string[];
  typewriter: { min: number; max: number };
}

export interface LoreBudgetSlider {
  min: number;
  max: number;
  step: number;
  stops: number[];
}

export interface SettingsPayload {
  ["Agent Settings"]?: {
    global?: {
      model?: { default_model?: string };
      narrative?: { test_mode?: boolean; test_database_suffix?: string };
    };
  };
  global?: {
    narrative?: { test_mode?: boolean; test_database_suffix?: string };
  };
  /** Raw role reference (e.g. "@openai.default"), not a resolved model ID. */
  apex?: { provider?: string; model?: string };
  wizard?: { default_model?: string; fallback_model?: string };
  lore?: {
    token_budget?: {
      apex_context_window?: number;
      system_prompt_tokens?: number;
    };
  };
  memnon?: {
    models?: Record<
      string,
      { is_active?: boolean; dimensions?: number; weight?: number }
    >;
  };
  /** Mirrors `[ui]` in nexus.toml (UISettings in settings_models.py). */
  ui?: {
    typewriter_ms_per_char?: number;
    theme?: ThemeId;
    fonts?: FontMatrix;
    lore_budget_slider?: LoreBudgetSlider;
  };
  settings_meta?: SettingsMeta;
}

/** The safe-to-edit subset accepted by PATCH /api/settings. */
export interface SettingsPatch {
  theme?: ThemeId;
  fonts?: Partial<Record<ThemeId, Partial<FontSlots>>>;
  typewriter_ms_per_char?: number;
  test_mode?: boolean;
  apex_model_ref?: string;
  wizard_model_ref?: string;
  apex_context_window?: number;
}
