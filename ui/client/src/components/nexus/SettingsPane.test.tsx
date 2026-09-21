import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { FontProvider, KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import {
  LOCAL_MODELS_DOWNLOAD_KEY,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import { SECRETS_QUERY_KEY } from "@/hooks/useSecrets";
import { applySettingsPatch, SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import type { LocalModelsStatus } from "@/types/localModels";
import type { SecretStatus } from "@/types/secrets";
import type { SettingsPayload } from "@/types/settings";
import { SettingsPane } from "./SettingsPane";

const SETTINGS: SettingsPayload = {
  global: { narrative: { test_mode: false } },
  ui: {
    theme: "veil",
    fonts: KEEPERS,
    typewriter_ms_per_char: 20,
  },
  settings_meta: {
    models: [],
    apex_allowed_providers: [],
    typewriter: { min: 1, max: 500 },
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
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], settings);
  queryClient.setQueryData([...SECRETS_QUERY_KEY], STATUSES);
  queryClient.setQueryData(["/api/dev/backstage/health"], gateOpen);

  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <FontProvider>
            <SettingsPane />
          </FontProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  localStorage.clear();
});

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

  it("renders catalog family rows instead of the registry model row", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData([...SETTINGS_QUERY_KEY], {
      ...SETTINGS,
      local_models: { model: "nousresearch/hermes-4-70b" },
      settings_meta: {
        typewriter: { min: 1, max: 500 },
        models: [
          {
            provider: "local",
            id: "nousresearch/hermes-4-70b",
            label: "Hermes 4 70B (Local)",
          },
        ],
        apex_allowed_providers: ["local"],
      },
    } satisfies SettingsPayload);
    queryClient.setQueryData([...SECRETS_QUERY_KEY], STATUSES);
    queryClient.setQueryData([...LOCAL_MODELS_STATUS_KEY], LOCAL_STATUS);
    queryClient.setQueryData([...LOCAL_MODELS_DOWNLOAD_KEY], { state: "idle" });

    render(
      <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <FontProvider>
            <SettingsPane />
          </FontProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("model-local-hermes-4.3-36b")).toBeInTheDocument();
    expect(screen.getByText("Hermes 4.3 36B")).toBeInTheDocument();
    // The registry model row is replaced by the family rows.
    expect(screen.queryByText("Hermes 4 70B (Local)")).not.toBeInTheDocument();
  });
});


describe("SettingsPane model IDs", () => {
  const settings: SettingsPayload = {
    ...SETTINGS,
    apex: { model: "frontier-2.1", provider: "openai" },
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

  it("takes provider routing from the roster when projecting a model choice", () => {
    const patched = applySettingsPatch(settings, {
      apex_model_id: "vendor/model-next",
      wizard_model_id: "vendor/model-next",
    });
    expect(patched.apex).toEqual({ model: "vendor/model-next", provider: "local" });
    expect(patched.wizard?.default_model).toBe("vendor/model-next");
    expect(() => applySettingsPatch(settings, {apex_model_id: "@openai.default"})).toThrow("Unknown model");
  });
});
