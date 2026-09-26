import { useInputDraft } from "@/hooks/useInputDraft";
import { readerDraftScope, readerDraftStore } from "@/lib/reader-draft";
import type { SlotState } from "@/types/narrative";

/**
 * Reader input keyed by story identity and the current input frontier, whose
 * choice identity is valid only against the choices slot state presents now.
 */
export function useReaderDraft(slotState: SlotState | undefined) {
  return useInputDraft(
    readerDraftStore,
    readerDraftScope(slotState),
    slotState?.choices.length ?? 0,
  );
}
