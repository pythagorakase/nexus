// DesignThemeRoot — the preview wrapper for design-sync cards (cfg.provider).
// Mounts the app's real providers so components that call useTheme/useFonts/
// useSettings render instead of throwing, and applies the Veil (.dark) theme +
// fonts. The fetch stub below mocks /api/settings (theme echoes each preview's
// localStorage), /api/secrets/status (API-key rows), and the character endpoints;
// retries are off so the render settles immediately. Exported through the Vite lib
// entry → window.NexusIris.DesignThemeRoot.
import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { FontProvider } from "@/contexts/FontContext";

// Headless preview fetch stub: feed the data-bound panes realistic mock data so
// they render populated instead of their empty state. GET-only — mutations fall
// through to the real fetch. /api/settings is mocked too (it drives the Theme/Font
// providers), but its theme echoes each preview's own localStorage, so deco/splash
// cards keep their theme and Veil cards stay Veil; everything else passes through.
if (typeof window !== "undefined" && !(window as any).__dsFetchStubbed) {
  (window as any).__dsFetchStubbed = true;
  const realFetch = window.fetch.bind(window);
  const json = (data: unknown) =>
    new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  const SLOTS = [
    { slot_number: 1, is_active: true, is_locked: false },
    { slot_number: 2, is_active: true, is_locked: false, wizard_in_progress: true, wizard_phase: "character" },
    { slot_number: 3, is_active: false, is_locked: false },
    { slot_number: 4, is_active: false, is_locked: false },
    { slot_number: 5, is_active: true, is_locked: true },
  ];
  const CAST = [
    { id: 1, name: "Mira Vané", summary: "A cartographer of the drowned districts, charting streets the tide reclaimed.", appearance: "Lean and weather-worn, ink-stained fingers, a coat patched with old chart-cloth.", personality: "Methodical, stubborn, quietly funny when the lanterns are low.", emotionalState: "Wary but resolved.", currentActivity: "Tracing a route toward the Spire.", currentLocationName: "The Drowned Plaza", portraitPath: null },
    { id: 2, name: "Cassius Brenn", summary: "A dock-warden who runs more than he guards.", appearance: "Broad, scarred, a brass warden's pin he no longer has the right to wear.", personality: "Affable, calculating, loyal to whoever paid last.", emotionalState: "Restless.", currentActivity: "Counting debts in the lantern-light.", currentLocationName: "Harbor Steps", portraitPath: null },
    { id: 3, name: "The Archivist", summary: "Keeper of the Spire's flooded records; speaks in retrieved fragments.", appearance: "Robed, ageless, eyes like wet glass.", personality: "Patient, oblique, unnervingly precise.", emotionalState: "Serene.", currentActivity: "Cataloguing what the water took.", currentLocationName: "The Spire Vaults", portraitPath: null },
  ];
  // API-key status rows (GET /api/secrets/status → SecretStatus[]). Masked
  // status only — no plaintext. A mixed present/absent set renders the KeysSection
  // card populated (present rows show a filled dot + ••••last4 placeholder); an
  // absent row shows the empty dot. Without this the query 404s and KeysSection's
  // `if (error) throw error` blanks the whole SettingsPane.
  const SECRETS = [
    { provider: "anthropic", account: "nexus-api", present: true, last4: "8f2a" },
    { provider: "openai", account: "nexus-api", present: true, last4: "b41c" },
    { provider: "openrouter", account: "nexus-api", present: false, last4: null },
  ];
  // Full settings payload; theme echoes the preview's own localStorage so the
  // Theme/Font providers don't override a deco/splash card's intended theme.
  const SETTINGS = (theme: string) => ({
    ui: {
      theme,
      fonts: {
        veil: { body: "Spectral", menu: "Cinzel", display: "Megrim" },
        gilded: { body: "Cormorant Garamond", menu: "Space Mono", display: "Monoton" },
        vector: { body: "Rajdhani", menu: "Source Code Pro", display: "Sixtyfour" },
      },
      lore_budget_slider: { min: 8000, max: 200000, step: 1000, stops: [8000, 32000, 64000, 128000, 200000] },
      typewriter_ms_per_char: 18,
    },
    apex: { model: "@anthropic.apex", provider: "anthropic" },
    lore: { token_budget: { apex_context_window: 128000 } },
    global: { narrative: { test_mode: false } },
    settings_meta: {
      model_roles: [
        { provider: "anthropic", role: "apex", ref: "@anthropic.apex", label: "Claude Opus 4.8" },
        { provider: "anthropic", role: "fast", ref: "@anthropic.fast", label: "Claude Sonnet 4.6" },
        { provider: "openai", role: "apex", ref: "@openai.apex", label: "GPT-5" },
      ],
      apex_allowed_providers: ["anthropic", "openai"],
      typewriter: { min: 0, max: 60 },
    },
  });
  // Local-model manager (/api/local-models). LocalModelRows does
  // `if (statusQuery.error && !status) throw statusQuery.error`, so an unmocked
  // status endpoint doesn't degrade the card — it throws and blanks every pane
  // that mounts it (SettingsPane embeds it). The catalog mirrors nexus.toml's
  // [local_models] so the cards show the real Hermes families.
  //
  // ONE scenario, deliberately: a card renders all its cells in a single page
  // load sharing one React Query cache, so every cell necessarily sees the same
  // payload — per-cell scenarios are impossible. This one is therefore tuned to
  // exercise the maximum number of row states at once. With system_ram_gb = 48:
  //   36b q4_k_m  installed + verified + active  -> active dot, EJECT row
  //   36b q6_k    installed + verified           -> ready, armed-delete trash
  //   36b q8_0    absent (min_ram 48, fits)      -> download arrow
  //   70b q4_k_m  download in flight             -> 37% + progress bar + cancel
  //   70b q6_k    min_ram 64 > 48                -> exceeds (RAM-ceiling tooltip)
  //   70b q8_0    min_ram 96 > 48                -> exceeds
  const LM_DIR = "~/.lmstudio/models/lmstudio-community";
  const LM_36B = `${LM_DIR}/Hermes-4.3-36B-GGUF`;
  const LM_70B = `${LM_DIR}/Hermes-4-70B-GGUF`;
  const LOCAL_STATUS = {
    models_dir: LM_DIR,
    system_ram_gb: 48,
    catalog: [
      { family: "hermes-4-70b", label: "Hermes 4 70B Q4_K_M", hf_repo: "lmstudio-community/Hermes-4-70B-GGUF", subdir: "Hermes-4-70B-GGUF", filename: "Hermes-4-70B-Q4_K_M.gguf", quant: "Q4_K_M", size_gb: 42.5, min_ram_gb: 48 },
      { family: "hermes-4-70b", label: "Hermes 4 70B Q6_K", hf_repo: "lmstudio-community/Hermes-4-70B-GGUF", subdir: "Hermes-4-70B-GGUF", filename: "Hermes-4-70B-Q6_K-00001-of-00002.gguf", quant: "Q6_K", size_gb: 57.9, min_ram_gb: 64 },
      { family: "hermes-4-70b", label: "Hermes 4 70B Q8_0", hf_repo: "lmstudio-community/Hermes-4-70B-GGUF", subdir: "Hermes-4-70B-GGUF", filename: "Hermes-4-70B-Q8_0-00001-of-00002.gguf", quant: "Q8_0", size_gb: 75.0, min_ram_gb: 96 },
      { family: "hermes-4.3-36b", label: "Hermes 4.3 36B Q4_K_M", hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF", subdir: "Hermes-4.3-36B-GGUF", filename: "NousResearch_Hermes-4.3-36B-Q4_K_M.gguf", quant: "Q4_K_M", size_gb: 21.8, min_ram_gb: 32 },
      { family: "hermes-4.3-36b", label: "Hermes 4.3 36B Q6_K", hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF", subdir: "Hermes-4.3-36B-GGUF", filename: "NousResearch_Hermes-4.3-36B-Q6_K.gguf", quant: "Q6_K", size_gb: 29.7, min_ram_gb: 40 },
      { family: "hermes-4.3-36b", label: "Hermes 4.3 36B Q8_0", hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF", subdir: "Hermes-4.3-36B-GGUF", filename: "NousResearch_Hermes-4.3-36B-Q8_0.gguf", quant: "Q8_0", size_gb: 38.4, min_ram_gb: 48 },
    ],
    // Installed iff models_dir/subdir/filename matches a row's path exactly;
    // `ready` is verified, not merely present.
    installed: [
      { path: `${LM_36B}/NousResearch_Hermes-4.3-36B-Q4_K_M.gguf`, filename: "NousResearch_Hermes-4.3-36B-Q4_K_M.gguf", arch: "seed_oss", quant: "Q4_K_M", size_bytes: 21_800_000_000, verified: true, active: true },
      { path: `${LM_36B}/NousResearch_Hermes-4.3-36B-Q6_K.gguf`, filename: "NousResearch_Hermes-4.3-36B-Q6_K.gguf", arch: "seed_oss", quant: "Q6_K", size_bytes: 29_700_000_000, verified: true, active: false },
    ],
    active: { gguf_path: `${LM_36B}/NousResearch_Hermes-4.3-36B-Q4_K_M.gguf`, ready: true, failed: false },
  };
  const LOCAL_DOWNLOAD = {
    state: "downloading",
    family: "hermes-4-70b",
    quant: "Q4_K_M",
    downloaded_bytes: 15_725_000_000,
    total_bytes: 42_500_000_000,
    progress: 0.37,
    files: ["Hermes-4-70B-Q4_K_M.gguf"],
    local_dir: LM_70B,
  };
  // GET-only: mutations (POST/PATCH/DELETE) fall through to the real fetch so a
  // preview that wires an interactive write fails visibly instead of silently
  // succeeding with mock data (Claude review).
  window.fetch = ((input: any, init?: any) => {
    const method = (init?.method ?? "GET").toUpperCase();
    const url = typeof input === "string" ? input : input?.url ?? "";
    if (method === "GET") {
      if (url.includes("/api/secrets/status")) return Promise.resolve(json(SECRETS));
      if (url.includes("/api/settings")) {
        const theme = window.localStorage.getItem("nexus-theme") || "veil";
        return Promise.resolve(json(SETTINGS(theme)));
      }
      if (url.includes("/api/local-models/download")) return Promise.resolve(json(LOCAL_DOWNLOAD));
      if (url.includes("/api/local-models/status")) return Promise.resolve(json(LOCAL_STATUS));
      if (url.includes("/api/story/new/slots")) return Promise.resolve(json(SLOTS));
      if (/\/api\/characters\/[^/]+\/images(\?|$)/.test(url)) return Promise.resolve(json([]));
      if (url.includes("/api/characters")) return Promise.resolve(json(CAST));
    }
    return realFetch(input as any, init);
  }) as typeof window.fetch;
}

export function DesignThemeRoot({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <FontProvider>
          <div
            className="dark"
            style={{
              background: "hsl(var(--background))",
              color: "hsl(var(--foreground))",
              fontFamily: "var(--font-sans)",
              padding: "1.5rem",
            }}
          >
            {children}
          </div>
        </FontProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
