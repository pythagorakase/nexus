import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { SlotState } from "@/types/narrative";
import { NarrativePane } from "./NarrativePane";

const TEXT = "  Léonie checks the ledger.\nKeep Sana’s note: 雨 🌙\n ";
const base: SlotState = {
  narrative_generation: {
    request_timeout_seconds: 10, poll_interval_seconds: 2,
    wake_gap_threshold_seconds: 15, stale_lease_timeout_seconds: 3600,
  },
  slot: 4, story_id: "2026-09-25T06:00:00+00:00", is_empty: false,
  is_wizard_mode: false, phase: null, subphase: null, thread_id: null,
  current_chunk_id: 12, has_pending: true, frontier_clock: null,
  storyteller_text: "The repair crew waits.", choices: ["Read the ledger", "Ask Sana"],
  session_id: "draft-12", model: "TEST",
};

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true, value: vi.fn(),
  });
});
beforeEach(() => localStorage.clear());

function mount(
  state: SlotState = base,
  send: NarrativeEngine["submitTurn"] = vi.fn(async () => true),
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  client.setQueryData(["/api/narrative/latest-chunk", state.slot], null);
  client.setQueryData(["/api/narrative/outline", state.slot], []);
  const engine: NarrativeEngine = {
    slotState: state, slotStateError: null, isSlotStateLoading: false,
    phase: null, skaldStatus: "READY", elapsedMs: 0, generationError: null,
    isGenerating: false, completedGenerations: 0, submitTurn: send,
  };
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <NarrativePane slot={state.slot} engine={engine} readingChunkId={null} onNavigate={vi.fn()} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

const input = () => screen.getByTestId("input-freeform");
const type = (text: string) => fireEvent.change(input(), { target: { value: text } });
const submit = () => fireEvent.keyDown(input(), { key: "Enter" });

describe("reader draft recovery", () => {
  it("restores exact unsent Unicode, whitespace and newlines after remount", () => {
    const view = mount();
    type(TEXT);
    view.unmount();
    const send = vi.fn(async () => true);
    mount(base, send);
    expect(input()).toHaveValue(TEXT);
    expect(send).not.toHaveBeenCalled();
  });

  it("does not carry drafts into another slot, story or frontier", () => {
    let view = mount();
    type(TEXT);
    view.unmount();
    for (const state of [
      { ...base, slot: 5 },
      { ...base, story_id: "new-story" },
      { ...base, session_id: "different-pending" },
      { ...base, has_pending: false, session_id: null },
    ]) {
      view = mount(state);
      expect(input()).toHaveValue("");
      view.unmount();
    }
    mount();
    expect(input()).toHaveValue(TEXT);
  });

  it("keeps a failed action through remount and clears only on successful manual retry", async () => {
    const failed = vi.fn(async () => false);
    const view = mount(base, failed);
    type(TEXT);
    submit();
    await waitFor(() => expect(failed).toHaveBeenCalledTimes(1));
    expect(input()).toHaveValue(TEXT);
    view.unmount();
    const accepted = vi.fn(async () => true);
    const retry = mount(base, accepted);
    expect(input()).toHaveValue(TEXT);
    expect(accepted).not.toHaveBeenCalled();
    submit();
    await waitFor(() => expect(input()).toHaveValue(""));
    expect(accepted).toHaveBeenCalledTimes(1);
    expect(accepted).toHaveBeenCalledWith({ userText: TEXT.trim() });
    retry.unmount();
    mount();
    expect(input()).toHaveValue("");
  });

  it("retains input until acknowledgement and does not submit twice", async () => {
    let accept!: (accepted: boolean) => void;
    const send = vi.fn(() => new Promise<boolean>((resolve) => { accept = resolve; }));
    mount(base, send);
    type(TEXT);
    submit();
    submit();
    expect(send).toHaveBeenCalledTimes(1);
    expect(input()).toHaveValue(TEXT);
    await act(async () => { accept(true); });
    expect(input()).toHaveValue("");
  });

  it("clears an accepted request after unmount without erasing a later frontier draft", async () => {
    let accept!: (accepted: boolean) => void;
    const send = vi.fn(() => new Promise<boolean>((resolve) => { accept = resolve; }));
    const view = mount(base, send);
    type(TEXT);
    submit();
    view.unmount();
    const next = mount({ ...base, session_id: "next-frontier" });
    type("My next action");
    await act(async () => { accept(true); });
    expect(input()).toHaveValue("My next action");
    next.unmount();
    mount();
    expect(input()).toHaveValue("");
  });

  it("does not let a delayed acknowledgement erase an edited revision", async () => {
    let accept!: (accepted: boolean) => void;
    mount(base, () => new Promise<boolean>((resolve) => { accept = resolve; }));
    type(TEXT);
    submit();
    type("A revised action");
    await act(async () => { accept(true); });
    expect(input()).toHaveValue("A revised action");
  });

  it("exposes an unconfirmed earlier action read-only when the frontier changed", async () => {
    const send = vi.fn(async () => false);
    const view = mount(base, send);
    type(TEXT);
    submit();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    view.unmount();
    const nextSend = vi.fn(async () => true);
    mount({ ...base, has_pending: false, session_id: null }, nextSend);
    expect(input()).toHaveValue("");
    expect(screen.getByLabelText("Saved unconfirmed action")).toHaveValue(TEXT);
    expect(screen.getByLabelText("Saved unconfirmed action")).toHaveAttribute("readonly");
    expect(nextSend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Dismiss saved action"));
    expect(screen.queryByTestId("unconfirmed-action")).not.toBeInTheDocument();
  });

  it("does not clear a typed draft when a structured choice fails", async () => {
    mount(base, vi.fn(async () => false));
    type(TEXT);
    fireEvent.click(screen.getByTestId("choice-1"));
    await act(async () => {});
    expect(input()).toHaveValue(TEXT);
  });

  it("reports unavailable browser persistence while retaining editable text", () => {
    mount();
    const storage = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError");
    });
    type(TEXT);
    expect(input()).toHaveValue(TEXT);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be saved");
    storage.mockRestore();
  });
});
