import type { SlotState } from "@/types/narrative";
import {
  createDraftStore,
  type DraftScope,
  type InputDraft,
  type UnconfirmedAction,
} from "@/lib/input-draft";

export const readerDraftStore = createDraftStore("reader");
export const READER_ACTION_CHANGED = readerDraftStore.actionChangedEvent;
export const READER_DRAFT_ACCEPTED = readerDraftStore.draftAcceptedEvent;

export type ReaderDraftScope = DraftScope;
export type ReaderDraft = InputDraft;
export type { UnconfirmedAction };

/** A pending generation and a committed chunk are different input frontiers. */
export function readerDraftScope(state: SlotState | undefined): ReaderDraftScope | null {
  if (!state?.story_id || state.is_empty || state.is_wizard_mode) return null;
  const frontier = state.has_pending
    ? state.session_id && ["pending", state.session_id]
    : state.current_chunk_id != null && ["committed", state.current_chunk_id];
  if (!frontier) return null;
  const story = JSON.stringify([state.slot, state.story_id]);
  return {
    draftKey: `${readerDraftStore.prefix}${story}:${JSON.stringify(frontier)}`,
    actionKey: `${readerDraftStore.prefix}${story}:unconfirmed`,
  };
}

/** Pairs `legacy->story_uuid` already migrated in this page's lifetime. */
const migratedStoryKeys = new Set<string>();

/**
 * Move drafts and stored actions keyed by the pre-UUID story id onto the
 * story_uuid keys, once, on first read (issue #822). An existing UUID-keyed
 * record is never overwritten; the legacy key is removed either way. A
 * storage failure leaves the pair unrecorded, and the draft load that follows
 * reports it.
 */
export function migrateLegacyReaderKeys(state: SlotState | undefined): void {
  const storyId = state?.story_id;
  const legacyId = state?.legacy_story_id;
  if (!state || !storyId || !legacyId || storyId === legacyId) return;
  const pair = `${legacyId}->${storyId}`;
  if (migratedStoryKeys.has(pair)) return;
  const oldPrefix = `${readerDraftStore.prefix}${JSON.stringify([state.slot, legacyId])}:`;
  const newPrefix = `${readerDraftStore.prefix}${JSON.stringify([state.slot, storyId])}:`;
  try {
    const legacyKeys: string[] = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(oldPrefix)) legacyKeys.push(key);
    }
    for (const oldKey of legacyKeys) {
      const rest = oldKey.slice(oldPrefix.length);
      const target = newPrefix + rest;
      if (localStorage.getItem(target) === null) {
        if (rest === "unconfirmed") {
          const actions = readerDraftStore.readUnconfirmedActions(oldKey).map((action) =>
            action.draftKey.startsWith(oldPrefix)
              ? { ...action, draftKey: newPrefix + action.draftKey.slice(oldPrefix.length) }
              : action);
          localStorage.setItem(target, JSON.stringify({ actions }));
        } else {
          const draft = readerDraftStore.readDraft(oldKey);
          if (draft) readerDraftStore.writeDraft(target, draft);
        }
      }
      localStorage.removeItem(oldKey);
    }
  } catch {
    return;
  }
  migratedStoryKeys.add(pair);
}

export const readReaderDraft = readerDraftStore.readDraft;
export const writeReaderDraft = readerDraftStore.writeDraft;
export const clearReaderDraft = readerDraftStore.clearDraft;
export const readUnconfirmedActions = readerDraftStore.readUnconfirmedActions;
export const writeUnconfirmedAction = readerDraftStore.writeUnconfirmedAction;
export const clearUnconfirmedAction = readerDraftStore.clearUnconfirmedAction;
