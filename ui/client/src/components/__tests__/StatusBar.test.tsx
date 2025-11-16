import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, beforeEach, afterEach, test, vi } from "vitest";

import { StatusBar } from "../StatusBar";

const toastSpy = vi.fn(() => ({
  dismiss: vi.fn(),
  update: vi.fn(),
}));

vi.mock("@/hooks/use-toast", () => ({
  toast: (...args: Parameters<typeof toastSpy>) => toastSpy(...args),
}));

const baseProps = {
  model: "OMEGA",
  modelId: "omega/full",
  season: 1,
  episode: 2,
  scene: 3,
  apexStatus: "READY" as const,
  isStoryMode: true,
};

const mockFetchResponse = (overrides?: Partial<Response>): Partial<Response> & { ok: boolean } => ({
  ok: true,
  json: async () => ({}),
  text: async () => "",
  ...overrides,
});

describe("StatusBar model controls", () => {
  beforeEach(() => {
    toastSpy.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("requests a model load when clicking while unloaded", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockFetchResponse());
    (globalThis as any).fetch = fetchMock;
    const onModelStatusChange = vi.fn();
    const onRefreshModelStatus = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <StatusBar
        {...baseProps}
        modelStatus="unloaded"
        onModelStatusChange={onModelStatusChange}
        onRefreshModelStatus={onRefreshModelStatus}
      />
    );

    const modelRegion = screen.getByTestId("text-model-status");
    await user.click(within(modelRegion).getByText("OMEGA"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/models/load",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: "omega/full" }),
      })
    );
    expect(onModelStatusChange).toHaveBeenNthCalledWith(1, "loading");
    expect(onModelStatusChange).toHaveBeenLastCalledWith("loaded");
    await waitFor(() => expect(onRefreshModelStatus).toHaveBeenCalled());
    expect(toastSpy).toHaveBeenCalled();
  });

  test("requests a model unload when clicking while loaded", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockFetchResponse());
    (globalThis as any).fetch = fetchMock;
    const onModelStatusChange = vi.fn();
    const onRefreshModelStatus = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <StatusBar
        {...baseProps}
        modelStatus="loaded"
        onModelStatusChange={onModelStatusChange}
        onRefreshModelStatus={onRefreshModelStatus}
      />
    );

    const modelRegion = screen.getByTestId("text-model-status");
    await user.click(within(modelRegion).getByText("OMEGA"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/models/unload",
      expect.objectContaining({
        method: "POST",
      })
    );
    expect(onModelStatusChange).toHaveBeenNthCalledWith(1, "loading");
    expect(onModelStatusChange).toHaveBeenLastCalledWith("unloaded");
    await waitFor(() => expect(onRefreshModelStatus).toHaveBeenCalled());
  });

  test("surfaces fetch failures and resets optimistic state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockFetchResponse({
        ok: false,
        text: async () => "boom",
      })
    );
    (globalThis as any).fetch = fetchMock;
    const onModelStatusChange = vi.fn();
    const onRefreshModelStatus = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <StatusBar
        {...baseProps}
        modelStatus="unloaded"
        onModelStatusChange={onModelStatusChange}
        onRefreshModelStatus={onRefreshModelStatus}
      />
    );

    const modelRegion = screen.getByTestId("text-model-status");
    await user.click(within(modelRegion).getByText("OMEGA"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(onModelStatusChange).toHaveBeenNthCalledWith(1, "loading");
    expect(onModelStatusChange).toHaveBeenLastCalledWith("unloaded");
    await waitFor(() => expect(onRefreshModelStatus).toHaveBeenCalled());
  });
});
