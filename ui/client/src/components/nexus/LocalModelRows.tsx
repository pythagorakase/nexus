/**
 * LocalModelRows - catalog-driven family rows for the `local` provider
 * group in the MODEL card (issue #465 Phase 1b, Claude Design prototype
 * "Local LLM Manager - Final").
 *
 * Each catalog family renders as a model-row with a chevron-expanded
 * quant list. Quant states: absent (download on click), downloading
 * (percent + cancel + thin progress bar), ready (STAGE on click,
 * two-stage armed delete), exceeds-RAM (dimmed, tooltip).
 *
 * Loading is gated behind an explicit APPLY (owner decision after
 * hands-on use): clicking a ready quant only stages it — these are
 * 20-75 GB models whose swaps take tens of seconds to minutes, so
 * nothing that heavy may ride on a single row click. APPLY activates
 * the staged quant and selects local as the storyteller; EJECT unloads
 * the serving model. Downloads stay direct: they never disturb the
 * serving model and carry their own cancel.
 *
 * Server truth arrives by polling; cadence comes from `[ui.local_models]`
 * in nexus.toml. Activation is fire-and-forget on the backend, so the
 * "swap in flight" state is derived from active.ready staying false —
 * polling fast until it flips (or fails, which surfaces as an alert).
 */
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownToLine,
  ChevronDown,
  Circle,
  CircleDot,
  Trash2,
  X,
} from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  LOCAL_MODELS_KNOB_DEFAULTS,
  LOCAL_MODELS_STATUS_KEY,
  useLocalDownloadStatus,
  useLocalModelActions,
  useLocalModelsStatus,
} from "@/hooks/useLocalModels";
import type {
  LocalCatalogEntry,
  LocalModelsStatus,
} from "@/types/localModels";
import type { LocalModelsUiKnobs } from "@/types/settings";

interface LocalModelRowsProps {
  /** True when settings.apex.model is the `@local.<role>` ref. */
  selected: boolean;
  /** Persists apex/wizard model refs (same mutation as other rows). */
  onPickLocal: () => void;
  knobs?: LocalModelsUiKnobs;
}

interface QuantView {
  entry: LocalCatalogEntry;
  path: string;
  installed: boolean;
  ready: boolean;
  isActive: boolean;
  isLoading: boolean;
  /** A persisted failed-activation record points at this quant. */
  hasFailedRecord: boolean;
  isDownloading: boolean;
  exceeds: boolean;
  progress: number;
}

function familyLabel(entry: LocalCatalogEntry): string {
  const suffix = ` ${entry.quant}`;
  return entry.label.endsWith(suffix)
    ? entry.label.slice(0, -suffix.length)
    : entry.label;
}

function quantPath(status: LocalModelsStatus, entry: LocalCatalogEntry): string {
  return `${status.models_dir}/${entry.subdir}/${entry.filename}`;
}

export function LocalModelRows({
  selected,
  onPickLocal,
  knobs,
}: LocalModelRowsProps) {
  const pollBusyMs = knobs?.poll_busy_ms ?? LOCAL_MODELS_KNOB_DEFAULTS.poll_busy_ms;
  const pollIdleMs = knobs?.poll_idle_ms ?? LOCAL_MODELS_KNOB_DEFAULTS.poll_idle_ms;
  const downloadPollMs =
    knobs?.download_poll_ms ?? LOCAL_MODELS_KNOB_DEFAULTS.download_poll_ms;
  const deleteArmMs =
    knobs?.delete_arm_ms ?? LOCAL_MODELS_KNOB_DEFAULTS.delete_arm_ms;

  const queryClient = useQueryClient();
  const actions = useLocalModelActions();

  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [armed, setArmed] = useState<string | null>(null);
  // Client-local staged quant path; APPLY is the only thing that loads it.
  const [staged, setStaged] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // In-flight action guard: server-derived guards (downloading, isLoading)
  // only flip after the POST's invalidation refetch lands, leaving a
  // ~100-300ms window where a second click double-POSTs and surfaces a
  // spurious 409/404 alert for an action that succeeded.
  const [pending, setPending] = useState(false);

  // Poll fast while a swap is in flight so active.ready flipping (or
  // failing) is seen promptly; idle cadence otherwise.
  const [statusPoll, setStatusPoll] = useState<number>(pollIdleMs);
  const statusQuery = useLocalModelsStatus(statusPoll);
  const status = statusQuery.data;
  const swapInFlight = Boolean(
    status?.active && !status.active.ready && !status.active.failed,
  );
  useEffect(() => {
    setStatusPoll(swapInFlight ? pollBusyMs : pollIdleMs);
  }, [swapInFlight, pollBusyMs, pollIdleMs]);

  const [downloadPoll, setDownloadPoll] = useState<number>(pollIdleMs);
  const downloadQuery = useLocalDownloadStatus(downloadPoll);
  const download = downloadQuery.data;
  const downloading = download?.state === "downloading";
  useEffect(() => {
    setDownloadPoll(downloading ? downloadPollMs : pollIdleMs);
  }, [downloading, downloadPollMs, pollIdleMs]);

  // A finished download changes the installed set; refresh status once on
  // the terminal transition (the record itself persists as done/failed).
  useEffect(() => {
    if (download?.state === "done" || download?.state === "failed") {
      void queryClient.invalidateQueries({
        queryKey: [...LOCAL_MODELS_STATUS_KEY],
      });
    }
  }, [download?.state, queryClient]);

  // Armed deletes disarm on their own after the configured window.
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(null), deleteArmMs);
    return () => clearTimeout(timer);
  }, [armed, deleteArmMs]);

  if (statusQuery.error && !status) throw statusQuery.error;

  const families = useMemo(() => {
    if (!status) return [];
    const byFamily = new Map<
      string,
      { label: string; quants: QuantView[] }
    >();
    const installedByPath = new Map(
      status.installed.map((model) => [model.path, model]),
    );
    for (const entry of status.catalog) {
      const path = quantPath(status, entry);
      const installed = installedByPath.get(path);
      const activeHere = status.active?.gguf_path === path;
      const view: QuantView = {
        entry,
        path,
        installed: Boolean(installed),
        ready: Boolean(installed?.verified),
        isActive: Boolean(activeHere && status.active?.ready),
        isLoading: Boolean(
          activeHere && !status.active?.ready && !status.active?.failed,
        ),
        hasFailedRecord: Boolean(activeHere && status.active?.failed),
        isDownloading: Boolean(
          download?.state === "downloading" &&
            download.family === entry.family &&
            download.quant === entry.quant,
        ),
        exceeds: entry.min_ram_gb > status.system_ram_gb,
        progress:
          download?.state === "downloading" &&
          download.family === entry.family &&
          download.quant === entry.quant
            ? download.progress
            : 0,
      };
      const group = byFamily.get(entry.family) ?? {
        label: familyLabel(entry),
        quants: [],
      };
      group.quants.push(view);
      byFamily.set(entry.family, group);
    }
    return Array.from(byFamily.entries());
  }, [status, download]);

  if (!status) {
    return (
      <li className="model-row lm-fam">
        <span className="caption dim">receiving</span>
      </li>
    );
  }

  const run = (task: () => Promise<unknown>) => {
    setPending(true);
    task()
      .catch((caught) => {
        setActionError(
          caught instanceof Error ? caught.message : String(caught),
        );
      })
      .finally(() => setPending(false));
  };

  const pickFamily = (quants: QuantView[]) => {
    const current = quants.find((q) => q.isActive || q.isLoading);
    if (current) {
      setActionError(null);
      onPickLocal();
      return;
    }
    // Nothing serving here: the click opens the quant list. Loading only
    // ever happens through APPLY on an explicitly staged quant.
    setOpen((state) => ({
      ...state,
      [quants[0].entry.family]: !state[quants[0].entry.family],
    }));
  };

  const clickQuant = (q: QuantView) => {
    if (pending || q.exceeds || q.isDownloading || q.isLoading) return;
    setActionError(null);
    if (q.isActive) {
      onPickLocal();
      return;
    }
    if (q.ready) {
      setStaged((current) => (current === q.path ? null : q.path));
      return;
    }
    if (!downloading) {
      run(() => actions.startDownload(q.entry.family, q.entry.quant));
    }
  };

  const failedError =
    status.active?.failed && status.active.error ? status.active.error : null;
  const downloadError =
    download?.state === "failed"
      ? (download.error ?? "download did not complete")
      : null;
  const alert = actionError
    ? { title: "ACTION REJECTED", text: actionError }
    : failedError
      ? { title: "LOAD FAILED", text: failedError }
      : downloadError
        ? { title: "DOWNLOAD FAILED", text: downloadError }
        : null;

  // A staged path is honored only while it still names a loadable,
  // non-serving quant in current server truth (a delete or an external
  // swap invalidates it silently).
  const stagedGroup = staged
    ? families.find(([, group]) =>
        group.quants.some(
          (q) => q.path === staged && q.ready && !q.exceeds && !q.isActive,
        ),
      )
    : undefined;
  const stagedQuant = stagedGroup?.[1].quants.find((q) => q.path === staged);
  const stagedLabel = stagedQuant
    ? `${stagedGroup![1].label.toLowerCase()} ${stagedQuant.entry.quant.toLowerCase()} · ${stagedQuant.entry.size_gb.toFixed(1)} gb`
    : null;
  const serving = Boolean(status.active && !status.active.failed);

  const applyStaged = () => {
    if (!stagedQuant || pending) return;
    setActionError(null);
    setStaged(null);
    run(() => actions.activate(stagedQuant.path));
    onPickLocal();
  };

  const eject = () => {
    if (pending) return;
    setActionError(null);
    run(() => actions.deactivate());
  };

  return (
    <TooltipProvider>
      {families.map(([family, group]) => {
        const activeQuant = group.quants.find((q) => q.isActive);
        const loadingQuant = group.quants.find((q) => q.isLoading);
        const shown = activeQuant ?? loadingQuant;
        const readyCount = group.quants.filter((q) => q.ready).length;
        const summary = shown
          ? `${shown.entry.quant.toLowerCase()} · ${shown.entry.size_gb.toFixed(1)} gb`
          : readyCount
            ? `${readyCount} on disk`
            : "";
        const on = selected && Boolean(shown);
        const isOpen = Boolean(open[family]);

        return (
          <Collapsible
            key={family}
            asChild
            open={isOpen}
            onOpenChange={(next) => setOpen((s) => ({ ...s, [family]: next }))}
          >
            <li className="lm-group">
              <div
                className={`model-row lm-fam ${on ? "on" : ""}`}
                onClick={() => pickFamily(group.quants)}
                data-testid={`model-local-${family}`}
              >
                <span className="model-radio">
                  {on ? <CircleDot size={12} /> : <Circle size={12} />}
                </span>
                <span className="model-name lm-name">{group.label}</span>
                {summary && (
                  <span className="caption dim lm-sum" data-testid={`lm-sum-${family}`}>
                    {summary}
                  </span>
                )}
                <span className="lm-spacer" />
                <button
                  className={`lm-chevron ${isOpen ? "open" : ""}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    setOpen((s) => ({ ...s, [family]: !isOpen }));
                  }}
                  aria-expanded={isOpen}
                  aria-label={`${group.label} quantizations`}
                  data-testid={`lm-toggle-${family}`}
                >
                  <ChevronDown size={13} />
                </button>
              </div>
              <CollapsibleContent className="lm-quants">
                <div
                  className="lm-quant-list"
                  role="radiogroup"
                  aria-label={`${group.label} quantizations`}
                >
                  {group.quants.map((q) => {
                    const blocked = !q.ready && !q.isDownloading && downloading;
                    const row = (
                      <div
                        key={q.entry.quant}
                        className={[
                          "lm-quant",
                          q.ready ? "ready" : "",
                          q.isActive ? "active" : "",
                          stagedQuant?.path === q.path ? "staged" : "",
                          q.isDownloading ? "dl" : "",
                          q.exceeds ? "exceeds" : "",
                          blocked ? "blocked" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={blocked ? undefined : () => clickQuant(q)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            if (!blocked) clickQuant(q);
                          }
                        }}
                        role="radio"
                        aria-checked={q.isActive}
                        aria-disabled={q.exceeds || blocked || undefined}
                        tabIndex={0}
                        data-testid={`lm-quant-${family}-${q.entry.quant}`}
                      >
                        <span className="lm-state">
                          {q.isDownloading ? (
                            <span className="lm-pct">
                              {Math.floor(q.progress * 100)}%
                            </span>
                          ) : q.isActive || q.isLoading ? (
                            <span
                              className={`lm-dot ${q.isLoading ? "loading" : ""}`}
                            />
                          ) : stagedQuant?.path === q.path ? (
                            <span className="lm-stage-mark" />
                          ) : !q.installed && !q.exceeds ? (
                            <ArrowDownToLine size={12} className="lm-get" />
                          ) : null}
                        </span>
                        <span className="caption lm-quant-label">
                          {q.entry.quant.toLowerCase()}
                        </span>
                        <span className="caption dim lm-size">
                          {q.entry.size_gb.toFixed(1)} gb
                        </span>
                        <span className="lm-action">
                          {q.ready && (
                            <button
                              className={`lm-trash ${armed === q.path ? "armed" : ""}`}
                              disabled={q.isActive || q.isLoading}
                              onClick={(event) => {
                                event.stopPropagation();
                                if (pending) return;
                                if (armed === q.path) {
                                  setArmed(null);
                                  // A failed-activation record pins the path
                                  // server-side (delete would 409 forever);
                                  // clear it first so the delete succeeds.
                                  run(
                                    q.hasFailedRecord
                                      ? async () => {
                                          await actions.deactivate();
                                          await actions.deleteModel(q.path);
                                        }
                                      : () => actions.deleteModel(q.path),
                                  );
                                } else {
                                  setArmed(q.path);
                                }
                              }}
                              aria-label={
                                armed === q.path
                                  ? `Confirm delete ${group.label} ${q.entry.quant}`
                                  : `Delete ${group.label} ${q.entry.quant}`
                              }
                              aria-pressed={armed === q.path}
                              data-testid={`lm-trash-${family}-${q.entry.quant}`}
                            >
                              <Trash2 size={11} />
                            </button>
                          )}
                          {q.isDownloading && (
                            <button
                              className="lm-cancel"
                              onClick={(event) => {
                                event.stopPropagation();
                                if (pending) return;
                                setActionError(null);
                                run(() => actions.cancelDownload());
                              }}
                              aria-label="Cancel download"
                              data-testid="lm-dl-cancel"
                            >
                              <X size={10} />
                            </button>
                          )}
                        </span>
                        {q.isDownloading && (
                          <span className="lm-bar">
                            <span
                              className="lm-bar-fill"
                              style={{ width: `${(q.progress * 100).toFixed(1)}%` }}
                            />
                          </span>
                        )}
                      </div>
                    );
                    return q.exceeds ? (
                      <Tooltip key={q.entry.quant}>
                        <TooltipTrigger asChild>{row}</TooltipTrigger>
                        <TooltipContent className="lm-tip" side="top">
                          needs {q.entry.min_ram_gb.toFixed(0)} gb ·{" "}
                          {status.system_ram_gb.toFixed(0)} gb memory
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      row
                    );
                  })}
                </div>
              </CollapsibleContent>
            </li>
          </Collapsible>
        );
      })}
      {(stagedQuant || serving) && (
        <li className="lm-group lm-actions" data-testid="lm-actions">
          {stagedLabel && (
            <span
              className="caption dim lm-staged-caption"
              data-testid="lm-staged-caption"
            >
              {stagedLabel}
            </span>
          )}
          <span className="lm-spacer" />
          {serving && (
            <button
              className="btn-soft"
              onClick={eject}
              aria-label="Unload the serving local model"
              data-testid="lm-eject"
            >
              EJECT
            </button>
          )}
          {stagedQuant && (
            <button
              className="btn-primary"
              onClick={applyStaged}
              aria-label={`Load ${stagedLabel ?? "staged quant"}`}
              data-testid="lm-apply"
            >
              APPLY
            </button>
          )}
        </li>
      )}
      {alert && (
        <li className="lm-group">
          <div className="alert danger lm-alert" data-testid="lm-alert">
            <AlertTriangle size={14} />
            <div>
              <div className="alert-title">{alert.title}</div>
              <div className="alert-body">{alert.text}</div>
            </div>
          </div>
        </li>
      )}
    </TooltipProvider>
  );
}

export const LOCAL_PROVIDER = "local";
