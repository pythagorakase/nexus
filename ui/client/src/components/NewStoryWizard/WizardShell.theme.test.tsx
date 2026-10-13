import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KEEPERS } from "@/contexts/FontContext";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { PREFERENCES_QUERY_KEY, SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import type { SettingsPayload } from "@/types/settings";
import { NewStoryWizard } from "./WizardShell";

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

/** The slot picker reads the slot list on mount; answer it, fail or pass the save. */
function spyFetch(answer: () => Response | Promise<Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if ((init?.method ?? "GET") === "GET" && String(input) === "/api/story/new/slots") {
      return new Response("[]", { status: 200 });
    }
    return answer();
  });
}

/** A theme switch made somewhere else, such as the Home menu, before the wizard opens. */
function ElsewhereSwitcher() {
  const { setTheme, saveError } = useTheme();
  return (
    <>
      <button onClick={() => setTheme("gilded")}>elsewhere-gilded</button>
      <output data-testid="save-error-probe">{saveError ?? "none"}</output>
    </>
  );
}

/** The wizard as /new-story renders it, with the real theme provider and query client. */
function renderWizard(withWizard = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], SETTINGS);
  queryClient.setQueryData([...PREFERENCES_QUERY_KEY], {
    theme: "veil", fonts: KEEPERS, wizard_model: "TEST",
  });
  const tree = (wizard: boolean) => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ElsewhereSwitcher />
        {wizard && <NewStoryWizard />}
      </ThemeProvider>
    </QueryClientProvider>
  );
  const view = render(tree(withWizard));
  return { showWizard: () => view.rerender(tree(true)) };
}

function openMenu() {
  fireEvent.keyDown(screen.getByRole("button", { expanded: false }), { key: "Enter" });
}

function item(label: string) {
  return screen.getByRole("menuitem", { name: new RegExp(`^${label}`) });
}

function pick(label: string) {
  fireEvent.click(item(label));
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("theme-gilded", "theme-vector", "theme-veil");
});

afterEach(() => vi.restoreAllMocks());

describe("wizard theme menu save failures (#961)", () => {
  it("shows an online HTTP rejection inside the open menu and keeps Veil checked", async () => {
    spyFetch(() => new Response("PermissionError: [Errno 13] Permission denied", { status: 500 }));
    renderWizard();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("wizard-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("500: PermissionError: [Errno 13] Permission denied");
    expect(screen.getByRole("menu")).toContainElement(alert);
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
    expect(item("Gilded")).toHaveTextContent(/^Gilded$/);
    expect(document.documentElement.classList.contains("theme-gilded")).toBe(false);
  });

  it("shows a network failure inside the open menu", async () => {
    spyFetch(() => { throw new TypeError("Failed to fetch"); });
    renderWizard();
    openMenu();
    pick("Gilded");

    const alert = await screen.findByTestId("wizard-theme-save-error");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("WRITE REJECTED");
    expect(alert).toHaveTextContent("Failed to fetch");
    await waitFor(() => expect(item("Veil")).toHaveTextContent("Veil ✓"));
  });

  it("shows a second rejection after a new pick cleared the first", async () => {
    const rejected = () =>
      new Response("PermissionError: [Errno 13] Permission denied", { status: 500 });
    let answerSave: () => Response | Promise<Response> = rejected;
    const fetchSpy = spyFetch(() => answerSave());
    const saves = () =>
      fetchSpy.mock.calls.filter(([, init]) => init?.method === "PATCH").length;
    renderWizard();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("wizard-theme-save-error");

    // Hold the second answer, so the cleared state is visible before it arrives.
    // The menu closes on the select, so read the cleared rejection from the context.
    let answer: (response: Response) => void = () => {};
    answerSave = () => new Promise<Response>((resolve) => { answer = resolve; });
    pick("Gilded");
    await waitFor(() => expect(saves()).toBe(2));
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("none"));

    answer(rejected());
    const alert = await screen.findByTestId("wizard-theme-save-error");
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
    renderWizard();
    openMenu();
    pick("Gilded");
    await screen.findByTestId("wizard-theme-save-error");

    fetchSpy.mockImplementation(async () => preferencesResponse("gilded"));
    pick("Gilded");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(screen.queryByTestId("wizard-theme-save-error")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(document.documentElement.classList.contains("theme-gilded")).toBe(true));

    openMenu();
    expect(item("Gilded")).toHaveTextContent("Gilded ✓");
    expect(item("Veil")).toHaveTextContent(/^Veil$/);
    expect(screen.queryByTestId("wizard-theme-save-error")).not.toBeInTheDocument();
  });

  it("opens on mount with a rejection that completed before the wizard opened", async () => {
    spyFetch(() => { throw new TypeError("Failed to fetch"); });
    const view = renderWizard(false);
    fireEvent.click(screen.getByText("elsewhere-gilded"));
    await waitFor(() =>
      expect(screen.getByTestId("save-error-probe")).toHaveTextContent("Failed to fetch"));

    view.showWizard();
    const alert = await screen.findByTestId("wizard-theme-save-error");
    expect(alert).toHaveTextContent("Failed to fetch");
    expect(screen.getByRole("menu")).toContainElement(alert);
  });

  it("keeps the success path: a pick saves, closes the menu and shows no alert", async () => {
    spyFetch(() => preferencesResponse("vector"));
    renderWizard();
    openMenu();
    pick("Vector");
    await waitFor(() =>
      expect(document.documentElement.classList.contains("theme-vector")).toBe(true));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wizard-theme-save-error")).not.toBeInTheDocument();
  });
});
