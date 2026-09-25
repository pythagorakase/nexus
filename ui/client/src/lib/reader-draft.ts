import type { SlotState } from "@/types/narrative";

const PREFIX = "nexus.reader-draft.v1:";
export const READER_ACTION_CHANGED = "nexus-reader-action-changed";
export const READER_DRAFT_ACCEPTED = "nexus-reader-draft-accepted";

export interface ReaderDraftScope {
  draftKey: string;
  actionKey: string;
}

export interface ReaderDraft {
  revision: string;
  text: string;
}

export interface UnconfirmedAction extends ReaderDraft {
  draftKey: string;
  attempt: string;
}

/** A pending generation and a committed chunk are different input frontiers. */
export function readerDraftScope(state: SlotState | undefined): ReaderDraftScope | null {
  if (!state?.story_id || state.is_empty || state.is_wizard_mode) return null;
  const frontier = state.has_pending
    ? state.session_id && ["pending", state.session_id]
    : state.current_chunk_id != null && ["committed", state.current_chunk_id];
  if (!frontier) return null;
  const story = JSON.stringify([state.slot, state.story_id]);
  return {
    draftKey: `${PREFIX}${story}:${JSON.stringify(frontier)}`,
    actionKey: `${PREFIX}${story}:unconfirmed`,
  };
}

function readRecord(key: string): Record<string, unknown> | null {
  const raw = localStorage.getItem(key);
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    // A malformed record is not a draft, and must never become player input.
    return null;
  }
}

export function readReaderDraft(key: string): ReaderDraft | null {
  const record = readRecord(key);
  return record && typeof record.revision === "string" && typeof record.text === "string"
    ? { revision: record.revision, text: record.text }
    : null;
}

export function writeReaderDraft(key: string, draft: ReaderDraft): void {
  if (draft.text) localStorage.setItem(key, JSON.stringify(draft));
  else localStorage.removeItem(key);
}

/** A delayed acknowledgement may clear only the revision it submitted. */
export function clearReaderDraft(key: string, revision: string): void {
  if (readReaderDraft(key)?.revision === revision) {
    localStorage.removeItem(key);
    window.dispatchEvent(new CustomEvent(READER_DRAFT_ACCEPTED, { detail: { key, revision } }));
  }
}

export function readUnconfirmedActions(key: string): UnconfirmedAction[] {
  const record = readRecord(key);
  const actions = Array.isArray(record?.actions) ? record.actions : record ? [record] : [];
  return actions.filter((action): action is UnconfirmedAction =>
    action && typeof action.revision === "string" && typeof action.text === "string"
    && typeof action.draftKey === "string" && typeof action.attempt === "string");
}

export function writeUnconfirmedAction(key: string, action: UnconfirmedAction): void {
  const actions = readUnconfirmedActions(key).filter((previous) =>
    previous.draftKey !== action.draftKey || previous.revision !== action.revision);
  localStorage.setItem(key, JSON.stringify({ actions: [...actions, action] }));
  window.dispatchEvent(new Event(READER_ACTION_CHANGED));
}

export function clearUnconfirmedAction(key: string, attempt: string): void {
  const actions = readUnconfirmedActions(key).filter((action) => action.attempt !== attempt);
  if (actions.length) localStorage.setItem(key, JSON.stringify({ actions }));
  else localStorage.removeItem(key);
  window.dispatchEvent(new Event(READER_ACTION_CHANGED));
}
