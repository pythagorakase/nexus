import { useCallback, useEffect, useRef, useState } from "react";
import type { DraftScope, DraftStore, InputDraft, UnconfirmedAction } from "@/lib/input-draft";

interface DraftState {
  key: string | null;
  draft: InputDraft;
  actions: UnconfirmedAction[];
  storageError: boolean;
}

function load(store: DraftStore, scope: DraftScope | null): DraftState {
  const empty = { revision: crypto.randomUUID(), text: "" };
  try {
    return {
      key: scope?.draftKey ?? null,
      draft: scope ? store.readDraft(scope.draftKey) ?? empty : empty,
      actions: scope ? store.readUnconfirmedActions(scope.actionKey) : [],
      storageError: false,
    };
  } catch {
    return { key: scope?.draftKey ?? null, draft: empty, actions: [], storageError: true };
  }
}

/** Persist exact input synchronously; no restore path ever submits a request. */
export function useInputDraft(store: DraftStore, scope: DraftScope | null) {
  const key = scope?.draftKey ?? null;
  const actionKey = scope?.actionKey ?? null;
  const [state, setState] = useState(() => load(store, scope));
  const submitting = useRef(false);
  // Derive a new scope before rendering its input, avoiding a stale-text frame
  // and avoiding an effect which could overwrite restored text on mount.
  if (state.key !== key) setState(load(store, scope));
  const current = state.key === key ? state : load(store, scope);
  // Memoized callbacks read the draft as it is at call time, not at memo time.
  const draftRef = useRef(current.draft);
  draftRef.current = current.draft;

  useEffect(() => {
    if (key === null || actionKey === null) return;
    const refreshAction = () => {
      try {
        const actions = store.readUnconfirmedActions(actionKey);
        setState((previous) => previous.key === key ? { ...previous, actions } : previous);
      } catch {
        setState((previous) => ({ ...previous, storageError: true }));
      }
    };
    const accepted = (event: Event) => {
      const { key: acceptedKey, revision } = (event as CustomEvent).detail;
      setState((previous) => previous.key === acceptedKey && previous.draft.revision === revision
        ? { ...previous, draft: { revision: crypto.randomUUID(), text: "" } } : previous);
    };
    const storage = (event: StorageEvent) => {
      refreshAction();
      if (event.key === key && event.newValue === null && event.oldValue) {
        try {
          accepted(new CustomEvent(store.draftAcceptedEvent, {
            detail: { key, revision: JSON.parse(event.oldValue).revision },
          }));
        } catch { /* Ignore malformed foreign records. */ }
      }
    };
    window.addEventListener(store.draftAcceptedEvent, accepted);
    window.addEventListener(store.actionChangedEvent, refreshAction);
    window.addEventListener("storage", storage);
    return () => {
      window.removeEventListener(store.draftAcceptedEvent, accepted);
      window.removeEventListener(store.actionChangedEvent, refreshAction);
      window.removeEventListener("storage", storage);
    };
  }, [store, key, actionKey]);

  const update = useCallback((text: string) => {
    const draft = { revision: crypto.randomUUID(), text };
    let storageError = false;
    try {
      if (key !== null) store.writeDraft(key, draft);
      else storageError = true;
    } catch {
      storageError = true;
    }
    setState((previous) => ({ ...previous, key, draft, storageError }));
  }, [store, key]);

  const submit = useCallback(async (
    send: () => Promise<boolean>,
    isFreeform: boolean,
  ): Promise<void> => {
    if (submitting.current) return;
    submitting.current = true;
    const draft = draftRef.current;
    const scoped = key !== null && actionKey !== null;
    const action: UnconfirmedAction | null = isFreeform && scoped
      ? { ...draft, draftKey: key, attempt: crypto.randomUUID() }
      : null;
    if (action && actionKey !== null) {
      try {
        store.writeUnconfirmedAction(actionKey, action);
      } catch {
        setState((previous) => ({ ...previous, storageError: true }));
      }
    }
    try {
      if (!await send()) return;
      // Runs even if the owner unmounted this component while the request
      // completed. The captured key/revision cannot erase a draft in another
      // story, frontier, conversation or phase.
      if (key !== null && actionKey !== null) {
        try {
          store.clearDraft(key, draft.revision);
          if (action) store.clearUnconfirmedAction(actionKey, action.attempt);
        } catch {
          setState((previous) => ({ ...previous, storageError: true }));
        }
      }
      setState((previous) => previous.key === key && previous.draft.revision === draft.revision
        ? { ...previous, draft: { revision: crypto.randomUUID(), text: "" } }
        : previous);
    } catch {
      // Transport errors normally resolve to false in the caller. Retain input
      // even if an unexpected rejection or browser-storage error occurs.
    } finally {
      submitting.current = false;
    }
  }, [store, key, actionKey]);

  const dismissAction = useCallback((attempt: string) => {
    if (actionKey === null) return;
    try {
      store.clearUnconfirmedAction(actionKey, attempt);
    } catch {
      setState((previous) => ({ ...previous, storageError: true }));
    }
  }, [store, actionKey]);

  return {
    text: current.draft.text,
    update,
    submit,
    // A response may advance the frontier or phase before its acknowledgement
    // arrives. Keep uncertain submissions readable, without replaying them as
    // new input or copying them into the new frontier's editable input.
    hasUnconfirmedAction: current.actions.length > 0,
    previousActions: current.actions.filter((action) =>
      action.draftKey !== key || action.revision !== current.draft.revision),
    dismissAction,
    storageError: current.storageError,
  };
}
