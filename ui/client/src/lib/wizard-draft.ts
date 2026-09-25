const PREFIX = "nexus.wizard-draft.v1:";
export const WIZARD_ACTION_CHANGED = "nexus-wizard-action-changed";
export const WIZARD_DRAFT_ACCEPTED = "nexus-wizard-draft-accepted";

export interface WizardDraftScope {
  draftKey: string;
  actionKey: string;
}

export interface WizardDraft {
  revision: string;
  text: string;
}

export interface UnconfirmedAction extends WizardDraft {
  draftKey: string;
  attempt: string;
}

/** Conversation identity changes for a fresh story, even in the same slot. */
export function wizardDraftScope(
  slot: number,
  threadId: string | null,
  phase: "setting" | "character" | "seed",
  characterState?: { concept?: unknown; trait_selection?: unknown; wildcard?: unknown } | null,
): WizardDraftScope | null {
  if (!threadId) return null;
  const subphase = phase !== "character" ? phase
    : characterState?.wildcard ? "sheet"
    : characterState?.trait_selection ? "wildcard"
    : characterState?.concept ? "traits" : "concept";
  const story = JSON.stringify([slot, threadId]);
  return {
    draftKey: `${PREFIX}${story}:${JSON.stringify([phase, subphase])}`,
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

export function readWizardDraft(key: string): WizardDraft | null {
  const record = readRecord(key);
  return record && typeof record.revision === "string" && typeof record.text === "string"
    ? { revision: record.revision, text: record.text }
    : null;
}

export function writeWizardDraft(key: string, draft: WizardDraft): void {
  if (draft.text) localStorage.setItem(key, JSON.stringify(draft));
  else localStorage.removeItem(key);
}

/** A delayed acknowledgement may clear only the revision it submitted. */
export function clearWizardDraft(key: string, revision: string): void {
  if (readWizardDraft(key)?.revision === revision) {
    localStorage.removeItem(key);
    window.dispatchEvent(new CustomEvent(WIZARD_DRAFT_ACCEPTED, { detail: { key, revision } }));
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
  window.dispatchEvent(new Event(WIZARD_ACTION_CHANGED));
}

export function clearUnconfirmedAction(key: string, attempt: string): void {
  const actions = readUnconfirmedActions(key).filter((action) => action.attempt !== attempt);
  if (actions.length) localStorage.setItem(key, JSON.stringify({ actions }));
  else localStorage.removeItem(key);
  window.dispatchEvent(new Event(WIZARD_ACTION_CHANGED));
}
