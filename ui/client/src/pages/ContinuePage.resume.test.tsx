import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Router, Route, Switch } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { afterEach, describe, expect, it, vi } from "vitest";
import ContinuePage from "./ContinuePage";
import { useSplashNavigation } from "./splash/shared";

vi.mock("@/contexts/ThemeContext", () => ({ useTheme: () => ({}) }));
vi.mock("@/components/ThemeMenu", () => ({ ThemeMenu: () => null }));
vi.mock("@/components/ai", () => ({
  Conversation: ({ children }: any) => <div>{children}</div>,
  ConversationContent: ({ children }: any) => <div>{children}</div>,
  ConversationScrollButton: () => null,
  Loader: () => <span role="status">Loading</span>,
  Response: ({ children }: any) => <div>{children}</div>,
}));

function Home() {
  const { handleContinue } = useSplashNavigation();
  return <button onClick={handleContinue}>CONTINUE</button>;
}

const setting = { world_name: "The Waking Wood", genre: "fantasy" };
const character = {
  concept: { name: "Mara", archetype: "Engineer", background: "Age 38.", suggested_traits: ["allies", "contacts", "patron"], trait_rationales: {} },
  trait_selection: { selected_traits: ["allies", "contacts", "patron"] },
  wildcard: { wildcard_name: "The bell", wildcard_description: "She hears it first." },
};
const sheet = { name: "Mara", summary: "Age 38. Maintains the old harbor machinery." };

function savedWizard(checkpoint: "setting" | "character", accepted: boolean) {
  const introduced = checkpoint === "setting" ? "character" : "seed";
  const withCharacter = checkpoint === "character";
  return {
    thread_id: "conv_saved",
    current_phase: accepted ? introduced : checkpoint,
    pending_confirmation: accepted ? null : checkpoint,
    awaiting_introduction: accepted ? introduced : null,
    artifact_token: accepted && !withCharacter ? null : "a".repeat(64),
    // The last saved turn is the player's; no confirmation or introduction exists yet.
    messages: [{ role: "assistant", content: "Anything else?" }, { role: "user", content: "That is everything." }],
    choices: [],
    setting_draft: setting,
    character_draft: withCharacter ? character : null,
    character_state: withCharacter ? character : null,
    character_sheet: withCharacter ? sheet : null,
    selected_seed: null,
    layer_draft: null,
    zone_draft: null,
    initial_location: null,
  };
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("resuming a wizard at a confirmation boundary (#955)", () => {
  it.each([
    { checkpoint: "character" as const, accepted: false, title: "Character", artifact: "Mara" },
    { checkpoint: "setting" as const, accepted: false, title: "Setting", artifact: "The Waking Wood" },
    { checkpoint: "character" as const, accepted: true, title: "Character", artifact: "Mara" },
    { checkpoint: "setting" as const, accepted: true, title: "Setting", artifact: "The Waking Wood" },
  ])("reload, Home → Continue and history keep the $checkpoint card (accepted: $accepted)", async ({ checkpoint, accepted, title, artifact }) => {
    localStorage.setItem("activeSlot", "5");
    const fetch = vi.fn(async (url: string) => {
      if (url === "/api/slot/5/state") return new Response(JSON.stringify({ is_empty: false, is_wizard_mode: true }));
      if (url === "/api/story/new/setup/resume?slot=5") return new Response(JSON.stringify(savedWizard(checkpoint, accepted)));
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    const location = memoryLocation({ path: "/continue" });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Router hook={location.hook}>
          <Switch>
            <Route path="/" component={Home} />
            <Route path="/continue" component={ContinuePage} />
          </Switch>
        </Router>
      </QueryClientProvider>,
    );

    const expectConfirmationBoundary = async () => {
      expect(await screen.findByRole("button", { name: "Confirm" }, { timeout: 2000 })).toBeEnabled();
      expect(screen.getByRole("heading", { name: title, level: 3 })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: artifact, level: 4 })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Revise" }) !== null).toBe(!accepted);
      expect(screen.getByTestId("wizard-freeform")).toBeDisabled();
      expect(screen.queryByTestId("wizard-choice-1")).toBeNull();
    };

    // Reload of /continue.
    await expectConfirmationBoundary();

    // Home → Continue.
    act(() => location.navigate("/"));
    fireEvent.click(screen.getByRole("button", { name: "CONTINUE" }));
    await expectConfirmationBoundary();

    // Leaving and returning through history remounts the same route.
    act(() => location.navigate("/"));
    expect(screen.getByRole("button", { name: "CONTINUE" })).toBeInTheDocument();
    act(() => location.navigate("/continue"));
    await expectConfirmationBoundary();

    // Resuming never confirms, revises, or requests inference.
    expect(new Set(fetch.mock.calls.map(([url]) => url))).toEqual(
      new Set(["/api/slot/5/state", "/api/story/new/setup/resume?slot=5"]),
    );
    expect(fetch).toHaveBeenCalledTimes(6);
  });
});
