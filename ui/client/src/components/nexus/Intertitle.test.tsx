import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Intertitle } from "./Intertitle";

function renderIntertitle(
  worldTime: string | null,
  worldTimeFace: string | null,
  worldLayer = "primary",
) {
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
          worldTimeFace={worldTimeFace}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("Intertitle", () => {
  it("renders scene grounding and a minute-precision world time", () => {
    renderIntertitle(
      "2087-11-03T22:47:00+00:00",
      "3 Nov 2087 · 22:47",
      "flashback",
    );

    expect(
      screen.getByText("S05E06 · Scene 13 · flashback layer"),
    ).toBeInTheDocument();
    expect(screen.getByText("3 Nov 2087 · 22:47")).toBeInTheDocument();
  });

  it("displays the server face without parsing the ISO instant", () => {
    renderIntertitle("2189-10-17T15:12:00-04:00", "17 Oct 2189 · 19:12");
    expect(screen.getByText("17 Oct 2189 · 19:12")).toHaveAttribute(
      "datetime",
      "2189-10-17T15:12:00-04:00",
    );
  });

  it("does not parse malformed ISO text in the reader", () => {
    renderIntertitle("invalid", "17 Oct 2189 · 19:12");
    expect(screen.getByText("17 Oct 2189 · 19:12")).toBeInTheDocument();
  });

  it("omits the second line when world time is unknown", () => {
    renderIntertitle(null, null);

    const intertitle = screen.getByTestId("intertitle");
    expect(intertitle).toHaveTextContent("S05E06 · Scene 13");
    expect(intertitle.querySelectorAll(".intertitle-copy > div")).toHaveLength(1);
  });
});
