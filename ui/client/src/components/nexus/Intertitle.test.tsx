import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Intertitle } from "./Intertitle";

function renderIntertitle(worldTime: string | null, worldLayer = "primary") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData(["/api/settings"], { ui: { theme: "veil" } });

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Intertitle
          season={5}
          episode={6}
          scene={13}
          worldLayer={worldLayer}
          worldTime={worldTime}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("Intertitle", () => {
  it("renders scene grounding and a minute-precision world time", () => {
    renderIntertitle("2087-11-03T22:47:00+00:00", "flashback");

    expect(
      screen.getByText("S05E06 · Scene 13 · flashback layer"),
    ).toBeInTheDocument();
    expect(screen.getByText("3 Nov 2087 · 22:47")).toBeInTheDocument();
  });

  it("omits the second line when world time is unknown", () => {
    renderIntertitle(null);

    const intertitle = screen.getByTestId("intertitle");
    expect(intertitle).toHaveTextContent("S05E06 · Scene 13");
    expect(intertitle.querySelectorAll(".intertitle-copy > div")).toHaveLength(1);
  });
});
