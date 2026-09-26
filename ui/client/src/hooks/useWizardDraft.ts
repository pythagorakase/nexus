import { useInputDraft } from "@/hooks/useInputDraft";
import { wizardDraftStore, type WizardDraftScope } from "@/lib/wizard-draft";

/** Wizard input keyed by conversation identity, phase and character subphase. */
export function useWizardDraft(scope: WizardDraftScope | null) {
  return useInputDraft(wizardDraftStore, scope);
}
