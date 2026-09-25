import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearReaderDraft,
  clearUnconfirmedAction,
  readReaderDraft,
  readerDraftScope,
  readUnconfirmedAction,
  READER_ACTION_CHANGED,
  writeReaderDraft,
  writeUnconfirmedAction,
  type ReaderDraft,
  type ReaderDraftScope,
  type UnconfirmedAction,
} from "@/lib/reader-draft";
import type { SlotState } from "@/types/narrative";

interface DraftState {
  key: string | null;
  draft: ReaderDraft;
  action: UnconfirmedAction | null;
  storageError: boolean;
}

function load(scope: ReaderDraftScope | null): DraftState {
  const empty = { revision: crypto.randomUUID(), text: "" };
  try {
    return {
      key: scope?.draftKey ?? null,
      draft: scope ? readReaderDraft(scope.draftKey) ?? empty : empty,
      action: scope ? readUnconfirmedAction(scope.actionKey) : null,
      storageError: false,
    };
  } catch {
    return { key: scope?.draftKey ?? null, draft: empty, action: null, storageError: true };
  }
}

/** Persist exact input synchronously; no restore path ever submits a request. */
export function useReaderDraft(slotState: SlotState | undefined) {
  const scope = readerDraftScope(slotState);
  const key = scope?.draftKey ?? null;
  const [state, setState] = useState(() => load(scope));
  const submitting = useRef(false);
  // Derive a new scope before rendering its input, avoiding a stale-text frame
  // and avoiding an effect which could overwrite restored text on mount.
  if (state.key !== key) setState(load(scope));
  const current = state.key === key ? state : load(scope);

  useEffect(() => {
    if (!scope) return;
    const refreshAction = () => {
      try {
        const action = readUnconfirmedAction(scope.actionKey);
        setState((previous) => previous.key === key ? { ...previous, action } : previous);
      } catch {
        setState((previous) => ({ ...previous, storageError: true }));
      }
    };
    window.addEventListener(READER_ACTION_CHANGED, refreshAction);
    window.addEventListener("storage", refreshAction);
    return () => {
      window.removeEventListener(READER_ACTION_CHANGED, refreshAction);
      window.removeEventListener("storage", refreshAction);
    };
  }, [key, scope?.actionKey]);

  const update = useCallback((text: string) => {
    const draft = { revision: crypto.randomUUID(), text };
    let storageError = false;
    try {
      if (scope) writeReaderDraft(scope.draftKey, draft);
      else storageError = true;
    } catch {
      storageError = true;
    }
    setState((previous) => ({ ...previous, key, draft, storageError }));
  }, [key, scope?.draftKey]);

  const submit = async (
    send: () => Promise<boolean>,
    isFreeform: boolean,
  ): Promise<void> => {
    if (submitting.current) return;
    submitting.current = true;
    const draft = current.draft;
    const action: UnconfirmedAction | null = isFreeform && scope
      ? { ...draft, draftKey: scope.draftKey, attempt: crypto.randomUUID() }
      : null;
    if (action && scope) {
      try {
        writeUnconfirmedAction(scope.actionKey, action);
        setState((previous) => ({ ...previous, action }));
      } catch {
        setState((previous) => ({ ...previous, storageError: true }));
      }
    }
    try {
      if (!await send()) return;
      // Runs even if Home unmounted this component while the request completed.
      // The captured key/revision cannot erase a draft in another story/frontier.
      if (scope) {
        try {
          clearReaderDraft(scope.draftKey, draft.revision);
          if (action) clearUnconfirmedAction(scope.actionKey, action.attempt);
        } catch {
          setState((previous) => ({ ...previous, storageError: true }));
        }
      }
      setState((previous) => previous.key === key && previous.draft.revision === draft.revision
        ? { ...previous, draft: { revision: crypto.randomUUID(), text: "" }, action: null }
        : previous);
    } catch {
      // Transport errors normally become false in useNarrativeEngine. Retain
      // input even if an unexpected rejection or browser-storage error occurs.
    } finally {
      submitting.current = false;
    }
  };

  const dismissAction = () => {
    if (!scope || !current.action) return;
    try {
      clearUnconfirmedAction(scope.actionKey, current.action.attempt);
      setState((previous) => ({ ...previous, action: null }));
    } catch {
      setState((previous) => ({ ...previous, storageError: true }));
    }
  };

  return {
    text: current.draft.text,
    update,
    submit,
    // Failed auto-approval can move the frontier. Keep that action readable,
    // without copying it into the new frontier's editable input.
    previousAction: current.action?.draftKey !== key ? current.action : null,
    dismissAction,
    storageError: current.storageError,
  };
}
