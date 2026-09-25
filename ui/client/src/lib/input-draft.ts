/**
 * Revisioned browser-storage drafts with an unconfirmed-action log.
 *
 * One generic store serves every input surface. A surface differs only by its
 * storage prefix and event names, both derived from `name`, and by how it maps
 * its own state onto a {@link DraftScope}.
 */

export interface DraftScope {
  draftKey: string;
  actionKey: string;
}

export interface InputDraft {
  revision: string;
  text: string;
}

export interface UnconfirmedAction extends InputDraft {
  draftKey: string;
  attempt: string;
}

export interface DraftStore {
  prefix: string;
  actionChangedEvent: string;
  draftAcceptedEvent: string;
  readDraft(key: string): InputDraft | null;
  writeDraft(key: string, draft: InputDraft): void;
  /** A delayed acknowledgement may clear only the revision it submitted. */
  clearDraft(key: string, revision: string): void;
  readUnconfirmedActions(key: string): UnconfirmedAction[];
  writeUnconfirmedAction(key: string, action: UnconfirmedAction): void;
  clearUnconfirmedAction(key: string, attempt: string): void;
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

export function createDraftStore(name: string): DraftStore {
  const actionChangedEvent = `nexus-${name}-action-changed`;
  const draftAcceptedEvent = `nexus-${name}-draft-accepted`;

  const readDraft = (key: string): InputDraft | null => {
    const record = readRecord(key);
    return record && typeof record.revision === "string" && typeof record.text === "string"
      ? { revision: record.revision, text: record.text }
      : null;
  };

  const readUnconfirmedActions = (key: string): UnconfirmedAction[] => {
    const record = readRecord(key);
    const actions = Array.isArray(record?.actions) ? record.actions : record ? [record] : [];
    return actions.filter((action): action is UnconfirmedAction =>
      action && typeof action.revision === "string" && typeof action.text === "string"
      && typeof action.draftKey === "string" && typeof action.attempt === "string");
  };

  return {
    prefix: `nexus.${name}-draft.v1:`,
    actionChangedEvent,
    draftAcceptedEvent,
    readDraft,
    writeDraft(key, draft) {
      if (draft.text) localStorage.setItem(key, JSON.stringify(draft));
      else localStorage.removeItem(key);
    },
    clearDraft(key, revision) {
      if (readDraft(key)?.revision === revision) {
        localStorage.removeItem(key);
        window.dispatchEvent(new CustomEvent(draftAcceptedEvent, { detail: { key, revision } }));
      }
    },
    readUnconfirmedActions,
    writeUnconfirmedAction(key, action) {
      const actions = readUnconfirmedActions(key).filter((previous) =>
        previous.draftKey !== action.draftKey || previous.revision !== action.revision);
      localStorage.setItem(key, JSON.stringify({ actions: [...actions, action] }));
      window.dispatchEvent(new Event(actionChangedEvent));
    },
    clearUnconfirmedAction(key, attempt) {
      const actions = readUnconfirmedActions(key).filter((action) => action.attempt !== attempt);
      if (actions.length) localStorage.setItem(key, JSON.stringify({ actions }));
      else localStorage.removeItem(key);
      window.dispatchEvent(new Event(actionChangedEvent));
    },
  };
}
