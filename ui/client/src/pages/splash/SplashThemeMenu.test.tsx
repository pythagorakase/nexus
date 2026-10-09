import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { PREFERENCES_QUERY_KEY, SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import type { SettingsPayload } from "@/types/settings";
import { SplashThemeMenu } from "./shared";

const SETTINGS: SettingsPayload = {
  ui: { theme: "veil", fonts: KEEPERS },
  settings_meta: { models: [], apex_allowed_providers: [] },
};

function preferencesResponse(theme: string): Response {
  return new Response(
    JSON.stringify({ theme, fonts: KEEPERS, wizard_model: "TEST" }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

/** Reads the shared theme context the way the Settings THEME card does. */
function SaveErrorProbe() {
  const { saveError } = useTheme();
  return <output data-testid="save-error-probe">{saveError ?? "none"}</output>;
}

function renderMenu() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], SETTINGS);
  queryClient.setQueryData([...PREFERENCES_QUERY_KEY], {
    theme: "veil", fonts: KEEPERS, wizard_model: "TEST",
  });
  const tree = (withMenu: boolean) => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        {withMenu && <SplashThemeMenu />}
        <SaveErrorProbe />
      </ThemeProvider>
    </QueryClientProvider>
  );
  const view = render(tree(true));
  return { rerender: (withMenu: boolean) => view.rerender(tree(withMenu)) };
}

function openMenu() {
  fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
}

function pick(label: string) {
  fireEvent.click(screen.getByRole("menuitem", { name: new RegExp(`^${label}`) }));
}

function checked(label: string) {
  return screen.getByRole("menuitem", { name: new RegExp(`^${label}`) });
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("theme-gilded", "theme-vector", "theme-veil");
});

afterEach(() => vi.restoreAllMocks());

describe("Home theme menu save failures (#961)", () => {
  it("shows an online HTTP rejection inside the reopened menu and keeps Veil checked", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return new Response("PermissionError: [Errno 13] Permission denied", { status: 500 });
    });
    renderMenu();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    expect(screen.getByRole("menu")).toContainElement(alert);
    await waitFor(() => expect(checked("Veil")).toHaveTextContent("Veil ✓"));
    expect(checked("Gilded")).toHaveTextContent(/^Gilded$/);
    expect(document.documentElement.classList.contains("theme-gilded")).toBe(false);
    expect(calls).toEqual(["PATCH /api/preferences"]);
  });

  it("shows a network failure inside the reopened menu", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      throw new TypeError("Failed to fetch");
    });
    renderMenu();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("Failed to fetch");
    await waitFor(() => expect(checked("Veil")).toHaveTextContent("Veil ✓"));
  });

  it("reopens on a second rejection after the first one cleared", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response("PermissionError: [Errno 13] Permission denied", { status: 500 }));
    renderMenu();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("splash-theme-save-error");

    pick("Gilded");
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
    const alert = await screen.findByTestId("splash-theme-save-error");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    await waitFor(() => expect(checked("Veil")).toHaveTextContent("Veil ✓"));
  });

  it.each([
    ["an HTTP 500", () => new Response("PermissionError", { status: 500 })],
    ["a network failure", () => { throw new TypeError("Failed to fetch"); }],
  ])("a successful retry after %s clears the alert, closes the menu and checks Gilded", async (
    _name, fail,
  ) => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => fail());
    renderMenu();
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
    expect(checked("Gilded")).toHaveTextContent("Gilded ✓");
    expect(checked("Veil")).toHaveTextContent(/^Veil$/);
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
  });

  it("leaves no rejection behind for Settings once Home unmounts", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      throw new TypeError("Failed to fetch");
    });
    const view = renderMenu();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("splash-theme-save-error");
    expect(screen.getByTestId("save-error-probe")).toHaveTextContent("Failed to fetch");

    view.rerender(false);
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("none"));
  });

  it("keeps the success path: a pick saves, closes the menu and shows no alert", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => preferencesResponse("vector"));
    renderMenu();
    openMenu();
    pick("Vector");
    await waitFor(() =>
      expect(document.documentElement.classList.contains("theme-vector")).toBe(true));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("splash-theme-save-error")).not.toBeInTheDocument();
  });
});
