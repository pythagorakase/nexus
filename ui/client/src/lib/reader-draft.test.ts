/**
 * The one-time move of reader drafts and stored actions from the pre-UUID
 * story id to story_uuid keys (issue #822).
 */
import { afterEach, describe, expect, it } from "vitest";
import {
  migrateLegacyReaderKeys,
  readerDraftScope,
  readReaderDraft,
  readUnconfirmedActions,
  writeReaderDraft,
  writeUnconfirmedAction,
} from "./reader-draft";
import type { SlotState } from "@/types/narrative";

const LEGACY = "player:1:2026-09-25T06:00:00+00:00";
const OTHER_LEGACY = "player:1:2026-08-01T09:30:00+00:00";

function slotState(storyId: string, legacyId: string | null, chunk = 12): SlotState {
  return {
    narrative_generation: {
      request_timeout_seconds: 10, poll_interval_seconds: 2,
      wake_gap_threshold_seconds: 15, stale_lease_timeout_seconds: 3600,
    },
    slot: 4, story_id: storyId, legacy_story_id: legacyId, is_empty: false,
    is_wizard_mode: false, phase: null, subphase: null, thread_id: null,
    current_chunk_id: chunk, has_pending: false, frontier_clock: null,
    storyteller_text: "The repair crew waits.", choices: ["Read the ledger"],
    session_id: null, model: "TEST",
  };
}

afterEach(() => localStorage.clear());

describe("legacy reader key migration", () => {
  it("moves a legacy draft and action to the UUID keys and removes the old keys", () => {
    const legacyScope = readerDraftScope(slotState(LEGACY, null))!;
    const draft = { revision: "r1", text: "  Ask about the gate.\n", choice: 1 };
    writeReaderDraft(legacyScope.draftKey, draft);
    writeUnconfirmedAction(legacyScope.actionKey, {
      ...draft, draftKey: legacyScope.draftKey, attempt: "a1",
    });

    const state = slotState("0b0e5e51-46a4-4c3b-9d3c-3f5f8c1d2e7a", LEGACY);
    migrateLegacyReaderKeys(state);

    const scope = readerDraftScope(state)!;
    expect(readReaderDraft(scope.draftKey)).toEqual(draft);
    expect(readUnconfirmedActions(scope.actionKey)).toEqual([
      { ...draft, draftKey: scope.draftKey, attempt: "a1" },
    ]);
    expect(localStorage.getItem(legacyScope.draftKey)).toBeNull();
    expect(localStorage.getItem(legacyScope.actionKey)).toBeNull();
  });

  it("leaves another legacy id in the same slot untouched", () => {
    const other = readerDraftScope(slotState(OTHER_LEGACY, null))!;
    writeReaderDraft(other.draftKey, { revision: "r2", text: "An older story." });

    migrateLegacyReaderKeys(slotState("5c1f3a7e-2d4b-4e8a-9b6c-7d8e9f0a1b2c", LEGACY));

    expect(readReaderDraft(other.draftKey)).toEqual({ revision: "r2", text: "An older story." });
  });

  it("never overwrites an existing UUID-keyed draft", () => {
    const legacyScope = readerDraftScope(slotState(LEGACY, null))!;
    writeReaderDraft(legacyScope.draftKey, { revision: "old", text: "Legacy text." });
    const state = slotState("9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d", LEGACY);
    const scope = readerDraftScope(state)!;
    writeReaderDraft(scope.draftKey, { revision: "new", text: "Newer text." });

    migrateLegacyReaderKeys(state);

    expect(readReaderDraft(scope.draftKey)).toEqual({ revision: "new", text: "Newer text." });
    expect(localStorage.getItem(legacyScope.draftKey)).toBeNull();
  });
});
