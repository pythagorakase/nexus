/**
 * Shape of the GET /api/settings payload (the Express layer serves
 * nexus.toml plus the legacy "Agent Settings" aliases it constructs).
 * Single source of truth for the client - extend here, not locally.
 */
export interface SettingsPayload {
  ["Agent Settings"]?: {
    global?: {
      model?: { default_model?: string };
      narrative?: { test_mode?: boolean };
    };
  };
  /** Mirrors `[ui]` in nexus.toml (UISettings in settings_models.py). */
  ui?: { typewriter_ms_per_char?: number };
}
