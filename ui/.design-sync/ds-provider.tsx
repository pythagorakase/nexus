// DesignThemeRoot — the preview wrapper for design-sync cards (cfg.provider).
// Mounts the app's real providers so components that call useTheme/useFonts/
// useSettings render instead of throwing, and applies the Veil (.dark) theme +
// fonts. The fetch stub below mocks /api/settings (theme echoes each preview's
// localStorage) and the character endpoints; retries are off so the render settles
// immediately. Exported through the Vite lib entry → window.NexusIris.DesignThemeRoot.
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
  // GET-only: mutations (POST/PATCH/DELETE) fall through to the real fetch so a
  // preview that wires an interactive write fails visibly instead of silently
  // succeeding with mock data (Claude review).
  window.fetch = ((input: any, init?: any) => {
    const method = (init?.method ?? "GET").toUpperCase();
    const url = typeof input === "string" ? input : input?.url ?? "";
    if (method === "GET") {
      if (url.includes("/api/settings")) {
        const theme = window.localStorage?.getItem("nexus-theme") || "veil";
        return Promise.resolve(json(SETTINGS(theme)));
      }
      if (url.includes("/api/story/new/slots")) return Promise.resolve(json(SLOTS));
      if (url.includes("/api/characters/") && url.includes("/images")) return Promise.resolve(json([]));
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
