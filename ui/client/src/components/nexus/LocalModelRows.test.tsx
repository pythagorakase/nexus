import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  LOCAL_MODELS_DOWNLOAD_KEY,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import { apiRequest } from "@/lib/queryClient";
import type {
  LocalDownloadStatus,
  LocalModelsStatus,
} from "@/types/localModels";
import { LocalModelRows } from "./LocalModelRows";

// The component's four write actions all flow through apiRequest; spying it
// is what lets these tests assert dispatches (method, URL, body) without a
// network. Mutation testing showed render-only assertions stay green when
// the dispatch wiring is deleted outright.
vi.mock("@/lib/queryClient", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/queryClient")>();
  return { ...actual, apiRequest: vi.fn() };
});
const apiRequestMock = vi.mocked(apiRequest);

beforeEach(() => {
  apiRequestMock.mockReset();
  apiRequestMock.mockResolvedValue(new Response("{}"));
});

const MODELS_DIR = "/models";

const STATUS: LocalModelsStatus = {
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
      family: "hermes-4.3-36b",
      label: "Hermes 4.3 36B Q6_K",
      hf_repo: "bartowski/NousResearch_Hermes-4.3-36B-GGUF",
      subdir: "Hermes-4.3-36B-GGUF",
      filename: "h36-q6.gguf",
      quant: "Q6_K",
      size_gb: 29.7,
      min_ram_gb: 40,
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
  installed: [
    {
      path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
      filename: "h36-q4.gguf",
      arch: "seed_oss",
      quant: "Q4_K_M",
      size_bytes: 21_800_000_000,
      verified: true,
      active: true,
    },
  ],
  active: {
    gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
    ready: true,
    failed: false,
  },
};

const IDLE: LocalDownloadStatus = { state: "idle" };

// STATUS plus a second installed, non-serving quant (its trash is enabled).
const WITH_Q6_INSTALLED: LocalModelsStatus = {
  ...STATUS,
  installed: [
    ...STATUS.installed,
    {
      path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q6.gguf`,
      filename: "h36-q6.gguf",
      arch: "seed_oss",
      quant: "Q6_K",
      size_bytes: 29_700_000_000,
      verified: true,
      active: false,
    },
  ],
};

// Idle-cadence knobs are irrelevant inside a test's lifetime; keep them
// huge so no poll fires mid-assertion.
const KNOBS = {
  poll_busy_ms: 60_000,
  poll_idle_ms: 60_000,
  download_poll_ms: 60_000,
  delete_arm_ms: 60_000,
};

function renderRows({
  status = STATUS,
  download = IDLE,
  selected = false,
  onPickLocal = () => {},
}: {
  status?: LocalModelsStatus;
  download?: LocalDownloadStatus;
  selected?: boolean;
  onPickLocal?: () => void;
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...LOCAL_MODELS_STATUS_KEY], status);
  queryClient.setQueryData([...LOCAL_MODELS_DOWNLOAD_KEY], download);

  render(
    <QueryClientProvider client={queryClient}>
      <ul>
        <LocalModelRows
          selected={selected}
          onPickLocal={onPickLocal}
          knobs={KNOBS}
        />
      </ul>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("LocalModelRows", () => {
  it("renders one family row per catalog family with quant-stripped labels", () => {
    renderRows();

    expect(screen.getByText("Hermes 4.3 36B")).toBeInTheDocument();
    expect(screen.getByText("Hermes 4 70B")).toBeInTheDocument();
    expect(screen.queryByText("Hermes 4.3 36B Q4_K_M")).not.toBeInTheDocument();
  });

  it("summarizes the serving quant on its family row", () => {
    renderRows();

    expect(screen.getByTestId("lm-sum-hermes-4.3-36b")).toHaveTextContent(
      "q4_k_m · 21.8 gb",
    );
  });

  it("marks the family radio on only when local is the picked provider", () => {
    renderRows({ selected: true });

    expect(screen.getByTestId("model-local-hermes-4.3-36b")).toHaveClass("on");
    // The 70B family serves nothing, so it never claims the radio.
    expect(screen.getByTestId("model-local-hermes-4-70b")).not.toHaveClass("on");
  });

  it("expands the quant list and classifies rows by state", () => {
    renderRows();

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4-70b"));

    const active = screen.getByTestId("lm-quant-hermes-4.3-36b-Q4_K_M");
    expect(active).toHaveClass("ready");
    expect(active).toHaveClass("active");
    expect(screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K")).not.toHaveClass(
      "ready",
    );
    // 96 GB requirement on a 48 GB fixture machine.
    expect(screen.getByTestId("lm-quant-hermes-4-70b-Q8_0")).toHaveClass(
      "exceeds",
    );
  });

  it("selects the family without a network write when its quant already serves", () => {
    const onPickLocal = vi.fn();
    renderRows({ onPickLocal });

    fireEvent.click(screen.getByTestId("model-local-hermes-4.3-36b"));

    expect(onPickLocal).toHaveBeenCalledTimes(1);
    expect(apiRequestMock).not.toHaveBeenCalled();
  });

  it("stages a ready quant on click without any network write", () => {
    const onPickLocal = vi.fn();
    renderRows({ status: WITH_Q6_INSTALLED, onPickLocal });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const row = screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K");
    fireEvent.click(row);

    expect(row).toHaveClass("staged");
    expect(screen.getByTestId("lm-staged-caption")).toHaveTextContent(
      "hermes 4.3 36b q6_k · 29.7 gb",
    );
    expect(apiRequestMock).not.toHaveBeenCalled();
    expect(onPickLocal).not.toHaveBeenCalled();
  });

  it("unstages on a second click and hides APPLY", () => {
    renderRows({ status: WITH_Q6_INSTALLED });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const row = screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K");
    fireEvent.click(row);
    expect(screen.getByTestId("lm-apply")).toBeInTheDocument();
    fireEvent.click(row);

    expect(row).not.toHaveClass("staged");
    expect(screen.queryByTestId("lm-apply")).not.toBeInTheDocument();
    expect(apiRequestMock).not.toHaveBeenCalled();
  });

  it("APPLY loads the staged quant and selects local as storyteller", () => {
    const onPickLocal = vi.fn();
    renderRows({ status: WITH_Q6_INSTALLED, onPickLocal });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    fireEvent.click(screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K"));
    fireEvent.click(screen.getByTestId("lm-apply"));

    expect(apiRequestMock).toHaveBeenCalledWith(
      "POST",
      "/api/local-models/activate",
      { path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q6.gguf` },
    );
    expect(onPickLocal).toHaveBeenCalledTimes(1);
  });

  it("EJECT unloads the serving model", () => {
    renderRows();

    fireEvent.click(screen.getByTestId("lm-eject"));

    expect(apiRequestMock).toHaveBeenCalledWith(
      "POST",
      "/api/local-models/deactivate",
    );
  });

  it("family click with nothing serving only toggles the quant list", () => {
    const onPickLocal = vi.fn();
    renderRows({
      status: { ...WITH_Q6_INSTALLED, active: null },
      onPickLocal,
    });

    fireEvent.click(screen.getByTestId("model-local-hermes-4.3-36b"));

    // The accordion opened (quant rows now in the document), but nothing
    // loaded and the storyteller selection did not move.
    expect(
      screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K"),
    ).toBeInTheDocument();
    expect(apiRequestMock).not.toHaveBeenCalled();
    expect(onPickLocal).not.toHaveBeenCalled();
  });

  it("starts a download when an absent quant is clicked", () => {
    renderRows();

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    fireEvent.click(screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K"));

    expect(apiRequestMock).toHaveBeenCalledWith(
      "POST",
      "/api/local-models/download",
      { family: "hermes-4.3-36b", quant: "Q6_K" },
    );
  });

  it("fires exactly one download on a rapid double click", () => {
    // Never-settling request keeps the in-flight guard armed across clicks.
    apiRequestMock.mockImplementation(() => new Promise(() => {}));
    renderRows();

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const row = screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K");
    fireEvent.click(row);
    fireEvent.click(row);

    expect(apiRequestMock).toHaveBeenCalledTimes(1);
  });

  it("arms the delete on first click instead of deleting", () => {
    renderRows({ status: WITH_Q6_INSTALLED });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const trash = screen.getByTestId("lm-trash-hermes-4.3-36b-Q6_K");
    fireEvent.click(trash);

    expect(trash).toHaveClass("armed");
    expect(trash).toHaveAttribute("aria-pressed", "true");
    expect(apiRequestMock).not.toHaveBeenCalled();
    // Still present: nothing was deleted, no error alert appeared.
    expect(screen.queryByTestId("lm-alert")).not.toBeInTheDocument();
  });

  it("deletes on the confirming second click", () => {
    renderRows({ status: WITH_Q6_INSTALLED });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const trash = screen.getByTestId("lm-trash-hermes-4.3-36b-Q6_K");
    fireEvent.click(trash);
    fireEvent.click(trash);

    expect(apiRequestMock).toHaveBeenCalledWith(
      "POST",
      "/api/local-models/delete",
      { path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q6.gguf` },
    );
  });

  it("disarms on its own after the configured window", () => {
    vi.useFakeTimers();
    try {
      renderRows({ status: WITH_Q6_INSTALLED });

      fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
      const trash = screen.getByTestId("lm-trash-hermes-4.3-36b-Q6_K");
      fireEvent.click(trash);
      expect(trash).toHaveClass("armed");

      act(() => {
        vi.advanceTimersByTime(KNOBS.delete_arm_ms + 1);
      });

      expect(trash).not.toHaveClass("armed");
      expect(apiRequestMock).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("routes a failed-activation quant's delete through deactivate", () => {
    renderRows({
      status: {
        ...WITH_Q6_INSTALLED,
        active: {
          gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q6.gguf`,
          ready: false,
          failed: true,
          error: "llama-server exited before becoming ready",
        },
      },
    });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));
    const trash = screen.getByTestId("lm-trash-hermes-4.3-36b-Q6_K");
    fireEvent.click(trash);
    fireEvent.click(trash);

    // The failed record pins the path server-side (delete would 409);
    // deactivate clears it, then the delete goes through.
    expect(apiRequestMock).toHaveBeenNthCalledWith(
      1,
      "POST",
      "/api/local-models/deactivate",
    );
  });

  it("disables the trash on the quant that is serving", () => {
    renderRows();

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));

    expect(screen.getByTestId("lm-trash-hermes-4.3-36b-Q4_K_M")).toBeDisabled();
  });

  it("renders percent, cancel, and progress bar for the downloading quant", () => {
    renderRows({
      download: {
        state: "downloading",
        family: "hermes-4.3-36b",
        quant: "Q6_K",
        downloaded_bytes: 12_474_000_000,
        total_bytes: 29_700_000_000,
        progress: 0.42,
        files: ["h36-q6.gguf"],
        local_dir: `${MODELS_DIR}/Hermes-4.3-36B-GGUF`,
      },
    });

    fireEvent.click(screen.getByTestId("lm-toggle-hermes-4.3-36b"));

    const row = screen.getByTestId("lm-quant-hermes-4.3-36b-Q6_K");
    expect(row).toHaveClass("dl");
    expect(row).toHaveTextContent("42%");
    expect(screen.getByTestId("lm-dl-cancel")).toBeInTheDocument();
  });

  it("surfaces a failed activation as a loud alert", () => {
    renderRows({
      status: {
        ...STATUS,
        active: {
          gguf_path: `${MODELS_DIR}/Hermes-4.3-36B-GGUF/h36-q4.gguf`,
          ready: false,
          failed: true,
          error: "llama-server exited before becoming ready",
        },
      },
    });

    expect(screen.getByTestId("lm-alert")).toHaveTextContent(
      "llama-server exited before becoming ready",
    );
  });
});
