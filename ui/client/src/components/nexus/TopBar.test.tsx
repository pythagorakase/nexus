import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LOCAL_MODELS_STATUS_KEY } from "@/hooks/useLocalModels";
import type { LocalModelsStatus } from "@/types/localModels";
import type { SlotState } from "@/types/narrative";
import { TopBar } from "./TopBar";

const MODELS_DIR = "/models";

const BASE: LocalModelsStatus = {
  models_dir: MODELS_DIR,
  system_ram_gb: 48,
  catalog: [
    {
      family: "hermes-4.3-36b",
      label: "Hermes 4.3 36B Q4_K_M",
      hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF",
      subdir: "Hermes-4.3-36B-GGUF",
      filename: "h36-q4.gguf",
      quant: "Q4_K_M",
      size_gb: 21.8,
      min_ram_gb: 32,
    },
    {
      family: "hermes-4-70b",
      label: "Hermes 4 70B Q8_0",
      hf_repo: "lmstudio-community/Hermes-4-70B-GGUF",
      subdir: "Hermes-4-70B-GGUF",
      filename: "h70-q8-00001-of-00002.gguf",
      quant: "Q8_0",
      size_gb: 75.0,
      min_ram_gb: 96,
    },
  ],
  installed: [],
  active: null,
};

function renderTopBar(
  status: LocalModelsStatus,
  frontierClock: SlotState["frontier_clock"] = null,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...LOCAL_MODELS_STATUS_KEY], status);
  // /api/settings intentionally unseeded: the meter must render from knob
  // defaults while settings are in flight.

  return render(
    <TopBar
      slot={1}
      characterName={null}
      skaldStatus="READY"
      frontierClock={frontierClock}
    />,
    {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      ),
    },
  );
}

describe("TopBar frontier clock", () => {
  it("renders the payload face unchanged and follows accepted frontier updates", () => {
    const frontier_clock = {
      instant: "2189-10-17T22:37:00Z",
      face: "17 Oct 2189 · 22:37",
    };
    const { rerender } = renderTopBar(BASE, frontier_clock);
    const clock = screen.getByTestId("frontier-clock");
    expect(clock).toHaveTextContent(frontier_clock.face);
    expect(clock).toHaveAttribute("datetime", frontier_clock.instant);
    expect(clock).not.toHaveAttribute("title");

    rerender(
      <TopBar
        slot={1}
        characterName={null}
        skaldStatus="GENERATING"
        frontierClock={{
          instant: "2189-10-17T22:42:00Z",
          face: "17 Oct 2189 · 22:42",
        }}
      />,
    );
    expect(screen.getByTestId("frontier-clock")).toHaveTextContent(
      "17 Oct 2189 · 22:42",
    );

    rerender(
      <TopBar
        slot={2}
        characterName={null}
        skaldStatus="READY"
        frontierClock={null}
      />,
    );
    expect(screen.queryByTestId("frontier-clock")).not.toBeInTheDocument();
  });

  it("has no clock element when there is no frontier", () => {
    renderTopBar(BASE);
    expect(screen.queryByTestId("frontier-clock")).not.toBeInTheDocument();
  });
});

describe("TopBar memory meter", () => {
  it("does not exist while no local model is active (hidden at rest)", () => {
    renderTopBar(BASE);

    expect(screen.queryByTestId("mem-meter")).not.toBeInTheDocument();
  });

  it("shows the serving quant's size against detected RAM", () => {
    renderTopBar({
      ...BASE,
      active: {
        gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
        ready: true,
        failed: false,
      },
    });

    expect(screen.getByTestId("mem-text")).toHaveTextContent("21.8 / 48 gb");
    const fill = screen
      .getByTestId("mem-meter")
      .querySelector(".mem-fill") as HTMLElement;
    expect(fill).not.toHaveClass("loading");
    // 21.8 decimal GB = 20.3 GiB of 48 GiB ≈ 42.3% — the GiB-converted
    // ratio, not the naive 21.8/48 = 45.4%.
    expect(parseFloat(fill.style.width)).toBeCloseTo(42.3, 0);
  });

  it("pulses while the swap is loading", () => {
    renderTopBar({
      ...BASE,
      active: {
        gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
        ready: false,
        failed: false,
      },
    });

    const fill = screen
      .getByTestId("mem-meter")
      .querySelector(".mem-fill") as HTMLElement;
    expect(fill).toHaveClass("loading");
  });

  it("vanishes when the activation failed", () => {
    renderTopBar({
      ...BASE,
      active: {
        gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
        ready: false,
        failed: true,
        error: "llama-server exited before becoming ready",
      },
    });

    expect(screen.queryByTestId("mem-meter")).not.toBeInTheDocument();
  });

  it("marks an over-budget model with the bronze fill", () => {
    renderTopBar({
      ...BASE,
      active: {
        gguf_path: `${MODELS_DIR}/Hermes-4-70B-GGUF/h70-q8-00001-of-00002.gguf`,
        ready: true,
        failed: false,
      },
    });

    const fill = screen
      .getByTestId("mem-meter")
      .querySelector(".mem-fill") as HTMLElement;
    // 75 decimal GB = 69.8 GiB > 48 GiB.
    expect(fill).toHaveClass("over");
    expect(parseFloat(fill.style.width)).toBe(100);
  });

  it("still exists with unknown size for an off-catalog serving model", () => {
    renderTopBar({
      ...BASE,
      active: {
        gguf_path: "/home/user/Downloads/mystery.gguf",
        ready: true,
        failed: false,
      },
    });

    expect(screen.getByTestId("mem-text")).toHaveTextContent("— / 48 gb");
  });
});
