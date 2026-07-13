/**
 * LocalModelRows - catalog-driven family rows for the `local` provider
 * group in the MODEL card (issue #465 Phase 1b, Claude Design prototype
 * "Local LLM Manager - Final").
 *
 * Each catalog family renders as a model-row with a chevron-expanded
 * quant list. Quant states: absent (download), downloading (percent +
 * cancel + thin progress bar), ready (activate on click, two-stage armed
 * delete), exceeds-RAM (dimmed, tooltip). Activating a quant also selects
 * the local provider as the storyteller model, mirroring the prototype.
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
  const [actionError, setActionError] = useState<string | null>(null);

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

  const run = (task: Promise<unknown>) => {
    task.catch((caught) => {
      setActionError(caught instanceof Error ? caught.message : String(caught));
    });
  };

  const pickFamily = (quants: QuantView[]) => {
    setActionError(null);
    const current = quants.find((q) => q.isActive || q.isLoading);
    if (current) {
      onPickLocal();
      return;
    }
    const best = quants
      .filter((q) => q.ready && !q.exceeds)
      .sort((a, b) => b.entry.size_gb - a.entry.size_gb)[0];
    if (best) {
      run(actions.activate(best.path));
      onPickLocal();
      return;
    }
    // Nothing runnable: open the quant list so the download menu is the
    // affordance the click lands on.
    setOpen((state) => ({ ...state, [quants[0].entry.family]: true }));
  };

  const clickQuant = (q: QuantView) => {
    setActionError(null);
    if (q.exceeds || q.isDownloading || q.isLoading) return;
    if (q.ready) {
      if (!q.isActive) run(actions.activate(q.path));
      onPickLocal();
      return;
    }
    if (!downloading) {
      run(actions.startDownload(q.entry.family, q.entry.quant));
    }
  };

  const failedError =
    status.active?.failed && status.active.error ? status.active.error : null;
  const downloadError =
    download?.state === "failed"
      ? (download.error ?? "download did not complete")
      : null;
  const alertText = actionError ?? failedError ?? downloadError;

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
                <div className="lm-quant-list">
                  {group.quants.map((q) => {
                    const blocked = !q.ready && !q.isDownloading && downloading;
                    const row = (
                      <div
                        key={q.entry.quant}
                        className={[
                          "lm-quant",
                          q.ready ? "ready" : "",
                          q.isActive ? "active" : "",
                          q.isDownloading ? "dl" : "",
                          q.exceeds ? "exceeds" : "",
                          blocked ? "blocked" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={blocked ? undefined : () => clickQuant(q)}
                        role="radio"
                        aria-checked={q.isActive}
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
                                if (armed === q.path) {
                                  setArmed(null);
                                  run(actions.deleteModel(q.path));
                                } else {
                                  setArmed(q.path);
                                }
                              }}
                              aria-label={`Delete ${group.label} ${q.entry.quant}`}
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
                                setActionError(null);
                                run(actions.cancelDownload());
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
      {alertText && (
        <li className="lm-group">
          <div className="alert danger lm-alert" data-testid="lm-alert">
            <AlertTriangle size={14} />
            <div>
              <div className="alert-title">LOCAL MODEL</div>
              <div className="alert-body">{alertText}</div>
            </div>
          </div>
        </li>
      )}
    </TooltipProvider>
  );
}

export const LOCAL_PROVIDER = "local";
