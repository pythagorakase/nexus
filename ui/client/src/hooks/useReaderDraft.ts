import { useInputDraft } from "@/hooks/useInputDraft";
import { readerDraftScope, readerDraftStore } from "@/lib/reader-draft";
import type { SlotState } from "@/types/narrative";

/** Reader input keyed by story identity and the current input frontier. */
export function useReaderDraft(slotState: SlotState | undefined) {
  return useInputDraft(readerDraftStore, readerDraftScope(slotState));
}
