import {
  createDraftStore,
  type DraftScope,
  type InputDraft,
  type UnconfirmedAction,
} from "@/lib/input-draft";

export const wizardDraftStore = createDraftStore("wizard");
export const WIZARD_ACTION_CHANGED = wizardDraftStore.actionChangedEvent;
export const WIZARD_DRAFT_ACCEPTED = wizardDraftStore.draftAcceptedEvent;

export type WizardDraftScope = DraftScope;
export type WizardDraft = InputDraft;
export type { UnconfirmedAction };

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
    draftKey: `${wizardDraftStore.prefix}${story}:${JSON.stringify([phase, subphase])}`,
    actionKey: `${wizardDraftStore.prefix}${story}:unconfirmed`,
  };
}

export const readWizardDraft = wizardDraftStore.readDraft;
export const writeWizardDraft = wizardDraftStore.writeDraft;
export const clearWizardDraft = wizardDraftStore.clearDraft;
export const readUnconfirmedActions = wizardDraftStore.readUnconfirmedActions;
export const writeUnconfirmedAction = wizardDraftStore.writeUnconfirmedAction;
export const clearUnconfirmedAction = wizardDraftStore.clearUnconfirmedAction;
