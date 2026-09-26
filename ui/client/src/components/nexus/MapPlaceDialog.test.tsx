import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { MapPlaceDialog } from "./MapPlaceDialog";
import type { Place } from "@shared/schema";

function makePlace(overrides: Partial<Place> = {}): Place {
  return {
    id: 950,
    name: "Old Pump Annex",
    type: "other",
    zone: 3,
    summary: null,
    history: null,
    currentStatus: null,
    inhabitants: null,
    secrets: null,
    coordinates: null,
    geom: null,
    extraData: {
      source: "retrograde",
      stub_kind: "retrograde_expansion_ref",
      sources: [{ plan: "event_plan", event_ref: "annex_quarantine" }],
    },
    createdAt: new Date("2026-09-25T00:00:00Z"),
    updatedAt: new Date("2026-09-25T00:00:00Z"),
    ...overrides,
  };
}

function renderDialog(place: Place) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/places", place.id, "images", 4], []);
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MapPlaceDialog
          place={place}
          zone={null}
          slot={4}
          open
          onOpenChange={vi.fn()}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("MapPlaceDialog", () => {
  it("shows a clear empty state for an incomplete place, including after remount", () => {
    const place = makePlace();
    const view = renderDialog(place);
    expect(screen.getByRole("dialog")).toHaveTextContent("Old Pump Annex");
    expect(screen.getByText("No details recorded yet.")).toBeInTheDocument();
    expect(
      screen.queryByText(/retrograde|canonical rows|latent/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Current Status")).not.toBeInTheDocument();
    view.unmount();
    renderDialog(place);
    expect(screen.getByText("No details recorded yet.")).toBeInTheDocument();
  });

  it("shows genuine summary, history and status despite retained stub provenance", () => {
    renderDialog(
      makePlace({
        summary: "The annex houses the station's reserve pumps.",
        history: "Built after the south-ring freeze.",
        currentStatus: "Workers are repairing the intake.",
      }),
    );
    for (const fact of [
      "The annex houses the station's reserve pumps.",
      "Built after the south-ring freeze.",
      "Workers are repairing the intake.",
    ]) {
      expect(screen.getByText(fact)).toBeInTheDocument();
    }
    expect(screen.queryByText("No details recorded yet.")).not.toBeInTheDocument();
  });

  it("treats whitespace-only prose as missing details", () => {
    renderDialog(
      makePlace({
        summary: " \n ",
        history: "\t",
        currentStatus: " ",
        secrets: "\n",
        inhabitants: [" "],
      }),
    );
    expect(screen.getByText("No details recorded yet.")).toBeInTheDocument();
    for (const section of [
      "Summary",
      "History",
      "Current Status",
      "Secrets",
      "Inhabitants",
    ]) {
      expect(screen.queryByText(section)).not.toBeInTheDocument();
    }
  });

  it.each([
    { history: "The Retrograde survey named the annex in 2180." },
    { secrets: "A spare valve is hidden behind the north panel." },
    { inhabitants: ["Sana Pell"] },
  ])("keeps sparse but genuine details visible: %j", (details) => {
    renderDialog(makePlace(details));
    expect(screen.queryByText("No details recorded yet.")).not.toBeInTheDocument();
    expect(screen.getByText(Object.values(details).flat()[0])).toBeInTheDocument();
  });
});
