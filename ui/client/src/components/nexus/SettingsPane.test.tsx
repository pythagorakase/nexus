import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FontProvider, KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import {
  LOCAL_MODELS_DOWNLOAD_KEY,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import { SECRETS_QUERY_KEY } from "@/hooks/useSecrets";
import { applySettingsPatch, SETTINGS_QUERY_KEY, PREFERENCES_QUERY_KEY } from "@/hooks/useSettings";
import { queryClient as settingsQueryClient } from "@/lib/queryClient";
import type { LocalModelsStatus } from "@/types/localModels";
import type { SecretStatus } from "@/types/secrets";
import type { SettingsPayload } from "@/types/settings";
import { SettingsPane } from "./SettingsPane";

const SETTINGS: SettingsPayload = {
  global: { narrative: { test_mode: false } },
  ui: {
    theme: "veil",
    fonts: KEEPERS,
  },
  settings_meta: {
    models: [],
    apex_allowed_providers: [],
  },
};

const STATUSES: SecretStatus[] = [
  { provider: "openai", account: "openai", present: true, last4: "wxyz" },
  {
    provider: "anthropic",
    account: "anthropic",
    present: false,
    last4: null,
  },
];

function renderPane(
  settings: SettingsPayload = SETTINGS,
  gateOpen: boolean = false,
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  }),
) {
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], settings);
  queryClient.setQueryData([...PREFERENCES_QUERY_KEY], {
    theme: settings.ui?.theme ?? "veil", fonts: settings.ui?.fonts ?? KEEPERS,
    wizard_model: settings.wizard?.default_model ?? "TEST",
  });
  queryClient.setQueryData(["/api/slot/4/settings"], {
    skald_model: settings.apex?.model ?? null, gaia_model: settings.apex?.gaia_model ?? null,
    apex_context_window: settings.lore?.token_budget?.apex_context_window ?? null,
  });
  queryClient.setQueryData([...SECRETS_QUERY_KEY], STATUSES);
  queryClient.setQueryData(["/api/dev/backstage/health"], gateOpen);

  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <FontProvider>
            <SettingsPane slot={4} />
          </FontProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  localStorage.clear();
  settingsQueryClient.clear();
});

afterEach(() => vi.restoreAllMocks());

describe("SettingsPane developer mode", () => {
  it("omits ADVANCED while the server gate is closed", () => {
    renderPane();

    expect(screen.queryByText(/ADVANCED/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("lever-dev-mode")).not.toBeInTheDocument();
  });

  it("persists the gate-visible developer lever locally", () => {
    renderPane(SETTINGS, true);

    const lever = screen.getByTestId("lever-dev-mode");
    expect(screen.getByText(/ADVANCED/)).toBeInTheDocument();
    expect(lever).toHaveAttribute("aria-checked", "false");
    fireEvent.click(lever);
    expect(lever).toHaveAttribute("aria-checked", "true");
    expect(localStorage.getItem("nexus-developer-mode")).toBe("true");
    expect(
      screen.getByText(
        /Exposes the story machinery — seat correspondence, state writes, Orrery activity/,
      ),
    ).toBeInTheDocument();
  });
});

describe("SettingsPane API keys", () => {
  it("renders registry rows with masked status and no textual status labels", () => {
    renderPane();

    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("anthropic")).toBeInTheDocument();
    expect(screen.getByTestId("key-input-openai")).toHaveAttribute(
      "placeholder",
      "••••••••wxyz",
    );
    expect(screen.getByTestId("key-status-openai")).toHaveClass("present");
    expect(screen.getByTestId("key-status-anthropic")).toHaveClass("absent");
    expect(screen.queryByText("present", { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByText("absent", { exact: false })).not.toBeInTheDocument();
  });

});

describe("SettingsPane model card local provider", () => {
  const LOCAL_STATUS: LocalModelsStatus = {
    models_dir: "/models",
    system_ram_gb: 128,
    catalog: [
      {
        family: "hermes-4.3-36b",
        label: "Hermes 4.3 36B Q4_K_M",
        hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF",
        subdir: "Hermes-4.3-36B-GGUF",
        filename: "h36-q4.gguf",
        quant: "Q4_K_M",
        size_gb: 21.8,
        min_ram_gb: 32,
      },
    ],
    installed: [],
    active: null,
  };

  it("keeps the shared local runtime manager under Skald only", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData([...SETTINGS_QUERY_KEY], {
      ...SETTINGS,
      local_models: { model: "nousresearch/hermes-4-70b" },
      settings_meta: {
        models: [
          {
            provider: "local",
            id: "nousresearch/hermes-4-70b",
            label: "Hermes 4 70B (Local)",
          },
          {
            provider: "openai",
            id: "remote-model",
            label: "Remote Model",
          },
        ],
        apex_allowed_providers: ["local", "openai"],
      },
    } satisfies SettingsPayload);
    queryClient.setQueryData([...PREFERENCES_QUERY_KEY], {
      theme: "veil", fonts: KEEPERS, wizard_model: "TEST",
    });
    queryClient.setQueryData(["/api/slot/4/settings"], {
      skald_model: null, gaia_model: null, apex_context_window: null,
    });
    queryClient.setQueryData([...SECRETS_QUERY_KEY], STATUSES);
    queryClient.setQueryData([...LOCAL_MODELS_STATUS_KEY], LOCAL_STATUS);
    queryClient.setQueryData([...LOCAL_MODELS_DOWNLOAD_KEY], { state: "idle" });

    render(
      <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <FontProvider>
            <SettingsPane slot={4} />
          </FontProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("model-local-hermes-4.3-36b")).toBeInTheDocument();
    expect(screen.getByText("Hermes 4.3 36B")).toBeInTheDocument();
    // The registry model row is replaced by the family rows.
    expect(screen.queryByText("Hermes 4 70B (Local)")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^World State / }));
    expect(screen.queryByTestId("model-local-hermes-4.3-36b"))
      .not.toBeInTheDocument();
    expect(screen.queryByText("Hermes 4 70B (Local)")).not.toBeInTheDocument();
    expect(screen.queryByText("local", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quantizations/ }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remote Model" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Same as Skald" }))
      .toBeInTheDocument();
    expect(screen.queryByText("Gaia", { exact: true })).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("model-target-skald"));
    expect(screen.getByTestId("model-local-hermes-4.3-36b")).toBeInTheDocument();
  });
});


describe("SettingsPane model IDs", () => {
  const settings: SettingsPayload = {
    ...SETTINGS,
    apex: {
      model: "frontier-2.1",
      provider: "openai",
      gaia_model: "vendor/model-next",
    },
    wizard: { default_model: "frontier-2.1" },
    settings_meta: {
      ...SETTINGS.settings_meta!,
      models: [
        { id: "frontier-2.1", label: "Frontier 2.1", provider: "openai" },
        { id: "vendor/model-next", label: "Model Next", provider: "openrouter" },
      ],
      apex_allowed_providers: ["openai", "openrouter"],
    },
  };

  it("shows every registered option without a role declaration", () => {
    renderPane(settings);
    expect(screen.getByTestId("model-openai-frontier-2.1")).toHaveClass("on");
    expect(screen.getByTestId("model-openrouter-vendor/model-next")).not.toHaveClass("on");
  });

  it("projects player preferences without changing story defaults", () => {
    const patched = applySettingsPatch(settings, { theme: "vector", wizard_model: "vendor/model-next" });
    expect(patched.apex).toEqual(settings.apex);
    expect(patched.ui?.theme).toBe("vector");
    expect(patched.wizard?.default_model).toBe("vendor/model-next");
  });

  it("shows both assignments and switches which model is selected", () => {
    renderPane(settings);
    expect(screen.getByTestId("model-target-skald")).toHaveTextContent(
      "Frontier 2.1",
    );
    expect(screen.getByTestId("model-target-gaia")).toHaveTextContent("Model Next");
    fireEvent.click(screen.getByTestId("model-target-gaia"));
    expect(screen.getByTestId("model-openai-frontier-2.1")).toHaveAttribute(
      "aria-pressed", "false",
    );
    expect(screen.getByTestId("model-openrouter-vendor/model-next"))
      .toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Same as Skald" }))
      .toHaveAttribute("aria-pressed", "false");
  });

  it("sends independent Gaia writes, clears to follow Skald, and retains that mode on Skald changes", async () => {
    const gaiaChanged = { skald_model: "frontier-2.1", gaia_model: "frontier-2.1", apex_context_window: null };
    const following = { ...gaiaChanged, gaia_model: null };
    const skaldChanged = { ...following, skald_model: "vendor/model-next" };
    const request = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(gaiaChanged)))
      .mockResolvedValueOnce(new Response(JSON.stringify(following)))
      .mockResolvedValueOnce(new Response(JSON.stringify(skaldChanged)));
    renderPane(settings, false, settingsQueryClient);

    fireEvent.click(screen.getByTestId("model-target-gaia"));
    fireEvent.click(screen.getByRole("button", { name: "Frontier 2.1" }));
    await waitFor(() =>
      expect(screen.getByTestId("model-target-gaia"))
        .toHaveTextContent("Frontier 2.1"),
    );
    expect(request).toHaveBeenNthCalledWith(
      1, "/api/slot/4/settings", expect.objectContaining({
        method: "PATCH", body: JSON.stringify({ gaia_model: "frontier-2.1" }),
      }),
    );
    expect(screen.getByTestId("model-target-skald")).toHaveTextContent(
      "Frontier 2.1",
    );

    fireEvent.click(screen.getByRole("button", { name: "Same as Skald" }));
    await waitFor(() =>
      expect(screen.getByTestId("model-target-gaia"))
        .toHaveTextContent("Same as Skald"),
    );
    expect(request).toHaveBeenNthCalledWith(
      2, "/api/slot/4/settings", expect.objectContaining({
        body: JSON.stringify({ gaia_model: null }),
      }),
    );
    expect(screen.getByRole("button", { name: "Frontier 2.1" }))
      .toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByTestId("model-target-skald"));
    fireEvent.click(screen.getByRole("button", { name: "Model Next" }));
    await waitFor(() =>
      expect(screen.getByTestId("model-target-skald"))
        .toHaveTextContent("Model Next"),
    );
    expect(request).toHaveBeenNthCalledWith(
      3, "/api/slot/4/settings", expect.objectContaining({
        body: JSON.stringify({
          skald_model: "vendor/model-next",
        }),
      }),
    );
    expect(settingsQueryClient.getQueryData(["/api/slot/4/settings"])).toEqual(skaldChanged);
    expect(settingsQueryClient.getQueryData(SETTINGS_QUERY_KEY)).toEqual(settings);
    expect(screen.getByTestId("model-target-gaia")).toHaveTextContent("Same as Skald");
  });

  it("restores the confirmed Gaia selection when the server rejects a write", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Write rejected", { status: 422 }),
    );
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderPane(settings, false, settingsQueryClient);
    fireEvent.click(screen.getByTestId("model-target-gaia"));
    fireEvent.click(screen.getByRole("button", { name: "Same as Skald" }));
    expect(await screen.findByText("WRITE REJECTED")).toBeInTheDocument();
    expect(screen.getByTestId("model-target-gaia")).toHaveTextContent("Model Next");
    expect(screen.getByTestId("model-target-skald")).toHaveTextContent(
      "Frontier 2.1",
    );
    expect(screen.getByTestId("model-openrouter-vendor/model-next"))
      .toHaveAttribute("aria-pressed", "true");
  });
});


describe("preference save failures (#961)", () => {
  function preferencesResponse(overrides: Record<string, unknown> = {}) {
    return new Response(
      JSON.stringify({ theme: "veil", fonts: KEEPERS, wizard_model: "TEST", ...overrides }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }

  it("shows the rejection for an online HTTP failure and keeps the saved font", async () => {
    const calls: string[] = [];
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return new Response("PermissionError: [Errno 13] Permission denied", { status: 500 });
    });
    renderPane();
    fireEvent.click(screen.getByRole("button", { name: "Cormorant Garamond" }));

    const alert = await screen.findByTestId("font-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    expect(screen.getByRole("button", { name: "Spectral" })).toHaveClass("on");
    expect(screen.getByRole("button", { name: "Cormorant Garamond" })).not.toHaveClass("on");
    expect(calls).toEqual(["PATCH /api/preferences"]);

    // Storage recovers: the same action succeeds, clears the error, and the
    // saved matrix now carries the new font.
    fetchSpy.mockImplementation(async () =>
      preferencesResponse({ fonts: { ...KEEPERS, veil: { ...KEEPERS.veil, body: "Cormorant Garamond" } } }));
    fireEvent.click(screen.getByRole("button", { name: "Cormorant Garamond" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Cormorant Garamond" })).toHaveClass("on"));
    expect(screen.queryByTestId("font-save-error")).not.toBeInTheDocument();
    expect(calls.filter((c) => !c.startsWith("PATCH /api/preferences"))).toEqual([]);
  });

  it("shows the rejection for a network failure and keeps the saved theme", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    renderPane();
    fireEvent.click(screen.getByTestId("theme-gilded"));

    const alert = await screen.findByTestId("theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("Failed to fetch");
    await waitFor(() => expect(screen.getByTestId("theme-veil")).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByTestId("theme-gilded")).toHaveAttribute("aria-pressed", "false");
    expect(document.documentElement.classList.contains("theme-gilded")).toBe(false);

    fetchSpy.mockResolvedValue(preferencesResponse({ theme: "gilded" }));
    fireEvent.click(screen.getByTestId("theme-gilded"));
    await waitFor(() => expect(screen.getByTestId("theme-gilded")).toHaveAttribute("aria-pressed", "true"));
    expect(screen.queryByTestId("theme-save-error")).not.toBeInTheDocument();
    expect(document.documentElement.classList.contains("theme-gilded")).toBe(true);
  });
});
