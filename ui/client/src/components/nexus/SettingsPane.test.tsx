import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FontProvider, KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SECRETS_QUERY_KEY } from "@/hooks/useSecrets";
import { SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
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
