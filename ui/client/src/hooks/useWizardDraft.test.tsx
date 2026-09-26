import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useWizardDraft } from "./useWizardDraft";
import { readWizardDraft, wizardDraftScope } from "@/lib/wizard-draft";

const setting = wizardDraftScope(4, "conversation-one", "setting")!;
const exactText = "  A harbor with a locked gate.\n\nKeep this last line.  ";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("wizard draft recovery", () => {
  it("restores exact unsent text after navigation or reload without submitting", () => {
    const first = renderHook(() => useWizardDraft(setting));
    act(() => first.result.current.update(exactText));
    expect(readWizardDraft(setting.draftKey)?.text).toBe(exactText);
    first.unmount();
    const resumed = renderHook(() => useWizardDraft(setting));
    expect(resumed.result.current.text).toBe(exactText);
    expect(resumed.result.current.previousActions).toEqual([]);
    expect(resumed.result.current.hasUnconfirmedAction).toBe(false);
  });

  it("isolates slots, fresh conversations, phases, and character subphases", () => {
    const { result, rerender } = renderHook(({ scope }) => useWizardDraft(scope), {
      initialProps: { scope: setting },
    });
    act(() => result.current.update(exactText));
    for (const scope of [
      wizardDraftScope(5, "conversation-one", "setting")!,
      wizardDraftScope(4, "conversation-two", "setting")!,
      wizardDraftScope(4, "conversation-one", "character")!,
      wizardDraftScope(4, "conversation-one", "seed")!,
    ]) {
      rerender({ scope });
      expect(result.current.text).toBe("");
    }
    const concept = wizardDraftScope(4, "conversation-one", "character")!;
    rerender({ scope: concept });
    act(() => result.current.update("A character concept"));
    const states = [{ concept: {} }, { trait_selection: {} }, { wildcard: {} }];
    const subphaseKeys = states.map((state) => wizardDraftScope(4, "conversation-one", "character", state)!);
    expect(new Set([concept.draftKey, ...subphaseKeys.map((scope) => scope.draftKey)]).size).toBe(4);
    for (const scope of subphaseKeys) {
      rerender({ scope });
      expect(result.current.text).toBe("");
    }
    rerender({ scope: setting });
    expect(result.current.text).toBe(exactText);
    expect(wizardDraftScope(4, null, "setting")).toBeNull();
  });

  it.each([false, "reject"])("retains text for failed or unknown submission: %s", async (outcome) => {
    const { result, unmount } = renderHook(() => useWizardDraft(setting));
    act(() => result.current.update(exactText));
    await act(() => result.current.submit(async () => {
      if (outcome === "reject") throw new Error("Connection interrupted");
      return false;
    }, true));
    expect(result.current.text).toBe(exactText);
    expect(result.current.hasUnconfirmedAction).toBe(true);
    unmount();
    const resumed = renderHook(() => useWizardDraft(setting));
    expect(resumed.result.current.text).toBe(exactText);
    expect(resumed.result.current.hasUnconfirmedAction).toBe(true);
  });

  it.each([true, false])("clears acknowledged freeform or choice alternatives only after acceptance: %s", async (isFreeform) => {
    const { result, unmount } = renderHook(() => useWizardDraft(setting));
    act(() => result.current.update(exactText));
    let finish!: (value: boolean) => void;
    let submitted!: Promise<void>;
    act(() => {
      submitted = result.current.submit(() => new Promise(resolve => { finish = resolve; }), isFreeform);
    });
    expect(result.current.text).toBe(exactText);
    await act(async () => { finish(true); await submitted; });
    expect(result.current.text).toBe("");
    expect(result.current.hasUnconfirmedAction).toBe(false);
    unmount();
    expect(renderHook(() => useWizardDraft(setting)).result.current.text).toBe("");
  });

  it.each([false, true])("late acknowledgement clears a restored revision but preserves later edits: %s", async (editAfterResume) => {
    const first = renderHook(() => useWizardDraft(setting));
    act(() => first.result.current.update(exactText));
    let finish!: (value: boolean) => void;
    let submitted!: Promise<void>;
    act(() => {
      submitted = first.result.current.submit(() => new Promise(resolve => { finish = resolve; }), true);
    });
    first.unmount();
    const resumed = renderHook(() => useWizardDraft(setting));
    if (editAfterResume) act(() => resumed.result.current.update("A later revision"));
    await act(async () => { finish(true); await submitted; });
    expect(resumed.result.current.text).toBe(editAfterResume ? "A later revision" : "");
    expect(readWizardDraft(setting.draftKey)?.text ?? "").toBe(editAfterResume ? "A later revision" : "");
    expect(resumed.result.current.hasUnconfirmedAction).toBe(false);
  });

  it("keeps multiple unconfirmed inputs readable across phase progress without replaying them", async () => {
    const { result, rerender } = renderHook(({ scope }) => useWizardDraft(scope), { initialProps: { scope: setting } });
    act(() => result.current.update(exactText));
    await act(() => result.current.submit(async () => false, true));
    const character = wizardDraftScope(4, "conversation-one", "character")!;
    rerender({ scope: character });
    expect(result.current.text).toBe("");
    expect(result.current.previousActions.map((action) => action.text)).toEqual([exactText]);
    act(() => result.current.update("Character input"));
    await act(() => result.current.submit(async () => false, true));
    rerender({ scope: wizardDraftScope(4, "conversation-one", "seed")! });
    expect(result.current.text).toBe("");
    expect(result.current.previousActions.map((action) => action.text)).toEqual([exactText, "Character input"]);
    act(() => result.current.dismissAction(result.current.previousActions[0].attempt));
    expect(result.current.previousActions.map((action) => action.text)).toEqual(["Character input"]);
    rerender({ scope: wizardDraftScope(4, "fresh-conversation", "seed")! });
    expect(result.current.previousActions).toEqual([]);
  });

  it("preserves in-memory input and reports unavailable browser storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Full"); });
    const { result } = renderHook(() => useWizardDraft(setting));
    act(() => result.current.update(exactText));
    expect(result.current.text).toBe(exactText);
    expect(result.current.storageError).toBe(true);
  });

  it("does not turn a malformed browser record into user input", () => {
    localStorage.setItem(setting.draftKey, JSON.stringify({ text: { arbitrary: "object" } }));
    expect(renderHook(() => useWizardDraft(setting)).result.current.text).toBe("");
  });
});
