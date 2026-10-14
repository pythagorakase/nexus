import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPane } from "@/components/nexus/SettingsPane";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import { FontProvider, KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { secretsQueryKey } from "@/hooks/useSecrets";
import { PREFERENCES_QUERY_KEY, SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import { HEALTH_QUERY_KEY } from "@/hooks/usePlane";
import type { SettingsPayload } from "@/types/settings";
import SplashPage from "../SplashPage";

const SETTINGS: SettingsPayload = {
  ui: { theme: "veil", fonts: KEEPERS },
  settings_meta: { models: [], apex_allowed_providers: [] },
};

const STATUS_URL = "/api/secrets/status?slot=4";

function preferencesResponse(theme: string): Response {
  return new Response(
    JSON.stringify({ theme, fonts: KEEPERS, wizard_model: "TEST" }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

/** The Settings pane re-reads key status on open; answer it, fail or pass the rest. */
function spyFetch(answer: () => Response | Promise<Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if ((init?.method ?? "GET") === "GET" && String(input) === STATUS_URL) {
      return new Response("[]", { status: 200 });
    }
    return answer();
  });
}

/** Reads the shared theme context the way the Settings THEME card does. */
function SaveErrorProbe() {
  const { saveError } = useTheme();
  return <output data-testid="save-error-probe">{saveError ?? "none"}</output>;
}

type View = "home" | "settings" | "away";

/** Home as the router renders it, with the real theme provider and query client. */
function renderHome() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], SETTINGS);
  // The Settings pane reads the serving plane from GET /health (824-S1); Home is the operator plane here.
  queryClient.setQueryData(HEALTH_QUERY_KEY, { status: "healthy", service: "narrative_api", plane: "operator" });
  queryClient.setQueryData([...PREFERENCES_QUERY_KEY], {
    theme: "veil", fonts: KEEPERS, wizard_model: "TEST",
  });
  queryClient.setQueryData(["/api/slot/4/settings"], {
    skald_model: null, gaia_model: null, apex_context_window: null,
  });
  queryClient.setQueryData(secretsQueryKey(4), []);
  queryClient.setQueryData(["/api/dev/backstage/health"], false);
  const tree = (view: View) => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <FontProvider>
            {view === "home" && <SplashPage />}
            {view === "settings" && <SettingsPane slot={4} />}
            <SaveErrorProbe />
          </FontProvider>
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
  const view = render(tree("home"));
  return { show: (next: View) => view.rerender(tree(next)) };
}

function menuTrigger() {
  return screen.getByRole("button", { expanded: false });
}

function openMenu() {
  fireEvent.keyDown(menuTrigger(), { key: "Enter" });
}

function item(label: string) {
  return screen.getByRole("menuitem", { name: new RegExp(`^${label}`) });
}

function pick(label: string) {
  fireEvent.click(item(label));
}

/**
 * jsdom has no canvas engine. The Veil splash draws its spiral on a 2D canvas,
 * so give it a context that accepts every call; drawing is not under test here.
 */
function stubCanvas() {
  const context = new Proxy({}, {
    get: (_target, prop) => (prop === "canvas" ? undefined : () => undefined),
    set: () => true,
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => context as unknown as CanvasRenderingContext2D,
  );
  vi.stubGlobal("Path2D", class { addPath() {} });
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("theme-gilded", "theme-vector", "theme-veil");
  stubCanvas();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Home theme menu save failures (#961)", () => {
  it("shows an online HTTP rejection inside the open menu and keeps Veil checked", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return new Response("PermissionError: [Errno 13] Permission denied", { status: 500 });
    });
    renderHome();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    expect(screen.getByRole("menu")).toContainElement(alert);
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
    expect(item("Gilded")).toHaveTextContent(/^Gilded$/);
    expect(document.documentElement.classList.contains("theme-gilded")).toBe(false);
    expect(calls).toEqual(["PATCH /api/preferences"]);
  });

  it("shows a network failure inside the open menu", async () => {
    spyFetch(() => { throw new TypeError("Failed to fetch"); });
    renderHome();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("Failed to fetch");
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
  });

  it("shows a second rejection after a new pick cleared the first", async () => {
    const rejected = () =>
      new Response("PermissionError: [Errno 13] Permission denied", { status: 500 });
    const fetchSpy = spyFetch(rejected);
    renderHome();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("splash-theme-save-error");

    // Hold the second answer, so the cleared state is visible before it arrives.
    // The menu closes on the select, so read the cleared rejection from the context.
    let answer: (response: Response) => void = () => {};
    fetchSpy.mockImplementation(() => new Promise<Response>((resolve) => { answer = resolve; }));
    pick("Gilded");
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("none"));

    answer(rejected());
    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    expect(screen.getByRole("menu")).toContainElement(alert);
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
  });

  it.each([
    ["an HTTP 500", () => new Response("PermissionError", { status: 500 })],
    ["a network failure", () => { throw new TypeError("Failed to fetch"); }],
  ])("a successful retry after %s clears the alert, closes the menu and checks Gilded", async (
    _name, fail,
  ) => {
    const fetchSpy = spyFetch(fail);
    renderHome();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("splash-theme-save-error");

    fetchSpy.mockImplementation(async () => preferencesResponse("gilded"));
    pick("Gilded");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(document.documentElement.classList.contains("theme-gilded")).toBe(true));
    expect(screen.getByTestId("save-error-probe")).toHaveTextContent("none");

    openMenu();
    expect(item("Gilded")).toHaveTextContent("Gilded ✓");
    expect(item("Veil")).toHaveTextContent(/^Veil$/);
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
  });

  it("shows a held rejection when Home mounts again, and Settings shows none", async () => {
    spyFetch(() => { throw new TypeError("Failed to fetch"); });
    const home = renderHome();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("splash-theme-save-error");

    // Leave Home and come back: the rejection is still held, so the menu opens on it.
    home.show("away");
    expect(screen.getByTestId("save-error-probe")).toHaveTextContent("Failed to fetch");
    home.show("home");
    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(screen.getByRole("menu")).toContainElement(alert);

    // Settings never inherits it: the THEME card clears it on mount.
    home.show("settings");
    await screen.findByTestId("theme-veil");
    expect(screen.queryByTestId("theme-save-error")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("none"));

    // Back on Home, nothing is held, so the menu stays closed.
    home.show("home");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
  });

  it("shows on return a rejection that completed while the player was elsewhere", async () => {
    let reject: (error: Error) => void = () => {};
    spyFetch(() => new Promise<Response>((_resolve, fail) => { reject = fail; }));
    const home = renderHome();
    openMenu();
    pick("Gilded");
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));

    home.show("away");
    reject(new TypeError("Failed to fetch"));
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("Failed to fetch"));

    home.show("home");
    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveTextContent("Failed to fetch");
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
  });

  it("keeps the success path: a pick saves, closes the menu and shows no alert", async () => {
    spyFetch(() => preferencesResponse("vector"));
    renderHome();
    openMenu();
    pick("Vector");
    await waitFor(() =>
      expect(document.documentElement.classList.contains("theme-vector")).toBe(true));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { expanded: false })).toHaveLength(1);
  });

  it("keeps the theme menu trigger first in the tab order on Home", async () => {
    renderHome();
    await userEvent.setup().tab();
    expect(menuTrigger()).toHaveFocus();
  });
});
