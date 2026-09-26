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

export const readReaderDraft = readerDraftStore.readDraft;
export const writeReaderDraft = readerDraftStore.writeDraft;
export const clearReaderDraft = readerDraftStore.clearDraft;
export const readUnconfirmedActions = readerDraftStore.readUnconfirmedActions;
export const writeUnconfirmedAction = readerDraftStore.writeUnconfirmedAction;
export const clearUnconfirmedAction = readerDraftStore.clearUnconfirmedAction;
