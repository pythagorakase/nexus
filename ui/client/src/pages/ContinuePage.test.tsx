import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Router, Route, Switch } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { afterEach, describe, expect, it, vi } from "vitest";
import ContinuePage from "./ContinuePage";
import { useSplashNavigation } from "./splash/shared";

vi.mock("@/components/NewStoryWizard/WizardShell", () => ({
  NewStoryWizard: ({ resumeSlot }: { resumeSlot: number }) => <p>Resuming wizard {resumeSlot}</p>,
}));

function Home() {
  const { handleContinue } = useSplashNavigation();
  return <button onClick={handleContinue}>CONTINUE</button>;
}

function renderNavigation(path = "/continue") {
  const location = memoryLocation({ path });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Router hook={location.hook}>
        <Switch>
          <Route path="/" component={Home} />
          <Route path="/continue" component={ContinuePage} />
          <Route path="/nexus"><p>Story reader for slot {localStorage.getItem("activeSlot")}</p></Route>
          <Route path="/new-story"><p>Choose a slot</p></Route>
        </Switch>
      </Router>
    </QueryClientProvider>,
  );
  return location;
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CONTINUE", () => {
  it("checks the most recently used slot and resumes its wizard directly", async () => {
    localStorage.setItem("activeSlot", "5");
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ is_empty: false, is_wizard_mode: true })));
    vi.stubGlobal("fetch", fetch);
    renderNavigation("/");
    fireEvent.click(screen.getByRole("button", { name: "CONTINUE" }));
    expect(await screen.findByText("Resuming wizard 5", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/slot/5/state");
  });

  it("opens the latest story and refreshes mode when Continue is used again", async () => {
    localStorage.setItem("activeSlot", "2");
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ is_empty: false, is_wizard_mode: false })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ is_empty: false, is_wizard_mode: true })));
    vi.stubGlobal("fetch", fetch);
    const location = renderNavigation();
    expect(await screen.findByText("Story reader for slot 2")).toBeInTheDocument();
    localStorage.setItem("activeSlot", "5");
    act(() => location.navigate("/continue"));
    expect(await screen.findByText("Resuming wizard 5")).toBeInTheDocument();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(["/api/slot/2/state", "/api/slot/5/state"]);
  });

  it.each([null, "banana", "9", "2junk"])("opens the slot picker for an invalid or absent saved slot (%s)", async value => {
    if (value !== null) localStorage.setItem("activeSlot", value);
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    renderNavigation();
    expect(await screen.findByText("Choose a slot")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("opens the slot picker if the remembered slot was cleared", async () => {
    localStorage.setItem("activeSlot", "5");
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ is_empty: true, is_wizard_mode: false })));
    vi.stubGlobal("fetch", fetch);
    renderNavigation();
    expect(await screen.findByText("Choose a slot")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/slot/5/state");
  });

  it("offers a retry for the same slot when state cannot be read", async () => {
    localStorage.setItem("activeSlot", "5");
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response("Unavailable", { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ is_empty: false, is_wizard_mode: true })));
    vi.stubGlobal("fetch", fetch);
    renderNavigation();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load Memory Slot 5");
    expect(localStorage.getItem("activeSlot")).toBe("5");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Resuming wizard 5")).toBeInTheDocument();
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(["/api/slot/5/state", "/api/slot/5/state"]);
  });
});
