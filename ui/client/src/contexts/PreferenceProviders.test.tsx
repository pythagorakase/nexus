/**
 * Theme and font providers read player preferences alone (#824, Decision
 * 824-Q3). GET /api/preferences is a player route; GET /api/settings is
 * operator-only, so on the player plane a provider that waited for it would
 * never apply the saved theme or fonts.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getQueryFn } from "@/lib/queryClient";
import { FontProvider, KEEPERS } from "./FontContext";
import { ThemeProvider } from "./ThemeContext";

const PREFERENCES = {
  theme: "gilded",
  fonts: { ...KEEPERS, gilded: { ...KEEPERS.gilded, body: "Spectral" } },
  wizard_model: "TEST",
};

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.removeAttribute("style");
});
afterEach(() => vi.unstubAllGlobals());

describe("preference providers", () => {
  it("applies saved theme and fonts from preferences alone", async () => {
    const fetchStub = vi.fn(async (input: unknown, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "GET" && String(input) === "/api/preferences") {
        return new Response(JSON.stringify(PREFERENCES), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${String(input)}`);
    });
    vi.stubGlobal("fetch", fetchStub);
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { queryFn: getQueryFn({ on401: "throw" }), retry: false, staleTime: Infinity },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <FontProvider>
            <span />
          </FontProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const root = document.documentElement;
    await waitFor(() => expect(root).toHaveClass("theme-gilded"));
    await waitFor(() =>
      expect(root.style.getPropertyValue("--font-narrative")).toBe("Spectral"),
    );
  });
});
