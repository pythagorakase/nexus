import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import { readerDraftScope } from "@/lib/reader-draft";
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
    phase: null, skaldStatus: "READY", elapsedMs: 0, generationError: null, failedGeneration: null, isRecoveryLoading: false, retryGeneration: vi.fn(async () => true),
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

  it("clears the restored same revision when acknowledgement arrives after remount", async () => {
    let accept!: (accepted: boolean) => void;
    const view = mount(base, () => new Promise<boolean>((resolve) => { accept = resolve; }));
    type(TEXT);
    submit();
    view.unmount();
    mount();
    expect(input()).toHaveValue(TEXT);
    await act(async () => { accept(true); });
    expect(input()).toHaveValue("");
  });

  it("retains earlier unconfirmed actions when another frontier send fails", async () => {
    let view = mount(base, async () => false);
    type(TEXT);
    submit();
    await act(async () => {});
    view.unmount();
    view = mount({ ...base, session_id: "second-frontier" }, async () => false);
    type("Second unconfirmed action");
    submit();
    await act(async () => {});
    expect(screen.getByLabelText("Saved unconfirmed action")).toHaveValue(TEXT);
    view.unmount();
    mount({ ...base, session_id: "third-frontier" });
    const saved = screen.getAllByLabelText("Saved unconfirmed action");
    expect(saved).toHaveLength(2);
    expect(saved[0]).toHaveValue(TEXT);
    expect(saved[1]).toHaveValue("Second unconfirmed action");
    fireEvent.click(screen.getAllByText("Dismiss saved action")[1]);
    expect(screen.getByLabelText("Saved unconfirmed action")).toHaveValue(TEXT);
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

  it("keeps a selected choice's draft and identity when its send fails", async () => {
    const failed = vi.fn(async () => false);
    mount(base, failed);
    fireEvent.click(screen.getByTestId("choice-1"));
    submit();
    await waitFor(() => expect(failed).toHaveBeenCalledTimes(1));
    expect(input()).toHaveValue("Read the ledger");
    expect(screen.getByTestId("choice-1")).toHaveAttribute("aria-pressed", "true");
    submit();
    await waitFor(() => expect(failed).toHaveBeenCalledTimes(2));
    expect(failed).toHaveBeenLastCalledWith({ choice: 1, userText: "Read the ledger" });
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

describe("number-key choice shortcuts", () => {
  const press = (init: KeyboardEventInit) =>
    fireEvent.keyDown(document.body, { key: "1", code: "Digit1", ...init });

  it.each([
    ["Cmd", { metaKey: true }],
    ["Ctrl", { ctrlKey: true }],
    ["Alt", { altKey: true }],
    ["held-key repeat", { repeat: true }],
    ["IME composition", { isComposing: true }],
  ])("never acts on a %s digit", async (_name, init) => {
    const send = vi.fn(async () => true);
    mount(base, send);
    press(init);
    await act(async () => {});
    expect(send).not.toHaveBeenCalled();
    expect(input()).toHaveValue("");
  });

  it("loads a plain digit's choice into the draft without sending", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    press({});
    await waitFor(() => expect(input()).toHaveValue("Read the ledger"));
    await act(async () => {});
    expect(send).not.toHaveBeenCalled();
    expect(input()).toHaveFocus();
  });
});

describe("deliberate choice drafts", () => {
  const choice = (n: number) => screen.getByTestId(`choice-${n}`);
  const sendGlyph = () => screen.getByRole("button", { name: "Send" });

  it("loads a clicked choice into the draft and sends only on Enter", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    fireEvent.click(choice(2));
    await act(async () => {});
    expect(send).not.toHaveBeenCalled();
    expect(input()).toHaveValue("Ask Sana");
    expect(input()).toHaveFocus();
    expect(choice(2)).toHaveAttribute("aria-pressed", "true");
    expect(choice(1)).toHaveAttribute("aria-pressed", "false");
    submit();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith({ choice: 2, userText: "Ask Sana" });
    await waitFor(() => expect(input()).toHaveValue(""));
    expect(choice(2)).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the selected identity while the text is edited", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    fireEvent.click(choice(1));
    type("Read the ledger, then burn it");
    expect(choice(1)).toHaveAttribute("aria-pressed", "true");
    expect(choice(1)).toHaveClass("selected", "edited");
    submit();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith({
      choice: 1, userText: "Read the ledger, then burn it",
    });
  });

  it("drops the selected identity when the text is cleared", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    fireEvent.click(choice(1));
    type("");
    expect(choice(1)).toHaveAttribute("aria-pressed", "false");
    type("Walk out");
    submit();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith({ userText: "Walk out" });
  });

  it("restores the selected identity with the draft after remount", async () => {
    const view = mount();
    fireEvent.click(choice(2));
    type("Ask Sana about the ledger");
    view.unmount();
    const send = vi.fn(async () => true);
    mount(base, send);
    expect(input()).toHaveValue("Ask Sana about the ledger");
    expect(choice(2)).toHaveAttribute("aria-pressed", "true");
    expect(send).not.toHaveBeenCalled();
    submit();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith({ choice: 2, userText: "Ask Sana about the ledger" });
  });

  it("sends through the icon-only send glyph, dimmed while empty", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    expect(sendGlyph()).toBeDisabled();
    expect(sendGlyph()).toHaveTextContent("↵");
    fireEvent.click(choice(1));
    expect(sendGlyph()).toBeEnabled();
    fireEvent.click(sendGlyph());
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    expect(send).toHaveBeenCalledWith({ choice: 1, userText: "Read the ledger" });
  });

  it("never sends on Shift+Enter or an Enter that ends IME composition", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    fireEvent.click(choice(1));
    fireEvent.keyDown(input(), { key: "Enter", shiftKey: true });
    fireEvent.keyDown(input(), { key: "Enter", isComposing: true });
    await act(async () => {});
    expect(send).not.toHaveBeenCalled();
  });

  it("turns a double Enter or a double click into one request", async () => {
    let accept!: (accepted: boolean) => void;
    const send = vi.fn(() => new Promise<boolean>((resolve) => { accept = resolve; }));
    mount(base, send);
    fireEvent.click(choice(1));
    submit();
    submit();
    fireEvent.click(sendGlyph());
    fireEvent.click(sendGlyph());
    expect(send).toHaveBeenCalledTimes(1);
    await act(async () => { accept(true); });
    expect(input()).toHaveValue("");
    expect(send).toHaveBeenCalledTimes(1);
  });

  it.each([0, 1.5, "2", null])(
    "treats a stored choice identity of %j as no draft at all",
    (stored) => {
      const key = readerDraftScope(base)!.draftKey;
      localStorage.setItem(key, JSON.stringify({ revision: "r1", text: "Ask Sana", choice: stored }));
      mount();
      expect(input()).toHaveValue("");
      expect(choice(2)).toHaveAttribute("aria-pressed", "false");
    },
  );

  it("replaces the draft when another choice is selected", async () => {
    const send = vi.fn(async () => true);
    mount(base, send);
    fireEvent.click(choice(1));
    type("Read the ledger aloud");
    fireEvent.click(choice(2));
    expect(input()).toHaveValue("Ask Sana");
    expect(choice(2)).toHaveClass("selected");
    expect(choice(2)).not.toHaveClass("edited");
    expect(choice(1)).not.toHaveClass("selected");
    expect(send).not.toHaveBeenCalled();
  });
});
