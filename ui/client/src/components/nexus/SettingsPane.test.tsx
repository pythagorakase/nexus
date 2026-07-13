import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FontProvider, KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import {
  LOCAL_MODELS_DOWNLOAD_KEY,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import { SECRETS_QUERY_KEY } from "@/hooks/useSecrets";
import { SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
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
    model_roles: [],
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

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], SETTINGS);
  queryClient.setQueryData([...SECRETS_QUERY_KEY], STATUSES);

  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <FontProvider>
          <SettingsPane />
        </FontProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

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

  it("renders catalog family rows instead of the registry role row", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData([...SETTINGS_QUERY_KEY], {
      ...SETTINGS,
      settings_meta: {
        typewriter: { min: 1, max: 500 },
        model_roles: [
          {
            ref: "@local.default",
            provider: "local",
            role: "default",
            model_id: "nousresearch/hermes-4-70b",
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
          <FontProvider>
            <SettingsPane />
          </FontProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("model-local-hermes-4.3-36b")).toBeInTheDocument();
    expect(screen.getByText("Hermes 4.3 36B")).toBeInTheDocument();
    // The registry role row is replaced by the family rows.
    expect(screen.queryByText("Hermes 4 70B (Local)")).not.toBeInTheDocument();
  });
});
