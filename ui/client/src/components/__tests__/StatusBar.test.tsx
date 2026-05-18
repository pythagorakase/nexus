import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ThemeProvider } from "@/contexts/ThemeContext";
import { StatusBar } from "../StatusBar";

const baseProps = {
  model: "OMEGA",
  season: 1,
  episode: 2,
  scene: 3,
  apexStatus: "READY" as const,
  isStoryMode: true,
};

function renderStatusBar(props: Partial<Parameters<typeof StatusBar>[0]> = {}) {
  return render(
    <ThemeProvider>
      <StatusBar {...baseProps} {...props} />
    </ThemeProvider>
  );
}

describe("StatusBar model display", () => {
  test("shows the configured model without lifecycle controls", async () => {
    const fetchMock = vi.fn();
    (globalThis as any).fetch = fetchMock;
    const user = userEvent.setup();

    renderStatusBar();

    const modelRegion = screen.getByTestId("text-model-status");
    expect(modelRegion).toHaveTextContent("MODEL:");
    expect(modelRegion).toHaveTextContent("OMEGA");

    await user.click(screen.getByText("OMEGA"));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("LOAD")).not.toBeInTheDocument();
    expect(screen.queryByText("UNLOAD")).not.toBeInTheDocument();
  });

  test("keeps generation progress tied to Skald status", () => {
    renderStatusBar({ apexStatus: "GENERATING" });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Model generating response..."
    );
  });
});
