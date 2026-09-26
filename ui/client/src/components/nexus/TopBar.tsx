/**
 * TopBar - the 52px operator strip across the top of the NexusLayout.
 *
 * Left: NEXUS wordmark (the single marquee-font element on this surface)
 * plus the slot label. Right: one frontier story clock at rest. Decision 8,
 * Option A (#857, #771) reverses "nothing at rest" for this element alone.
 * Per visual minimalism the persistent `SKALD <status>` is gone - it carried
 * an internal module name, sat on screen while idle, and during generation
 * restated the in-reader status line and the ledger telemetry. The one
 * state with no other surface is backend unreachability, which renders as
 * a plain OFFLINE flag only while true. Per the locked design decisions
 * there is no scene cartouche and no MODEL field.
 *
 * The memory meter (issue #465) follows the same rule: it exists only
 * while a managed local model is serving or loading, and vanishes when
 * no local model is active. Fill is the active quant's on-disk weight
 * size against detected system RAM - live process telemetry cannot see
 * Metal-wired mmap pages, so static catalog sizes are the honest signal
 * (see _system_ram_gb in local_models_endpoints.py).
 *
 * The strip also carries the generation announcer (#777): a visually hidden
 * polite status region that tells assistive technology when a turn starts,
 * completes, or fails. It has no visible text, so it adds nothing to the
 * quiet chrome.
 */
import { useEffect, useReducer } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LOCAL_MODELS_KNOB_DEFAULTS,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import type { LocalModelsStatus } from "@/types/localModels";
import type { SettingsPayload } from "@/types/settings";
import type { FrontierClock, SkaldStatus } from "@/types/narrative";

interface TopBarProps {
  slot: number | null;
  characterName: string | null;
  skaldStatus: SkaldStatus;
  frontierClock: FrontierClock | null;
}

/** Spoken by the generation announcer; never rendered visibly. */
const GENERATION_ANNOUNCEMENTS = {
  started: "Generation started",
  complete: "Generation complete",
  failed: "Generation failed",
} as const;

interface AnnouncerState {
  /** A turn this surface saw start has not yet reached an outcome. */
  inFlight: boolean;
  message: string;
}

/**
 * Fold one operator-status observation into the announcer.
 *
 * The engine derives SkaldStatus from its generation state: TRANSMITTING and
 * GENERATING while a turn runs, RECEIVING (held briefly) only when the turn
 * completed, and READY once the phase clears without completion, which is
 * the failed-turn path (a durable error or a submission that never started).
 * An outcome is announced only for a turn seen starting, so the RECEIVING
 * flash that replays the latest finished session on load stays silent.
 * OFFLINE is connectivity, not an outcome: the turn stays in flight and is
 * resolved by whatever status follows reconnection.
 */
function announce(state: AnnouncerState, status: SkaldStatus): AnnouncerState {
  switch (status) {
    case "TRANSMITTING":
    case "GENERATING":
      return state.inFlight
        ? state
        : { inFlight: true, message: GENERATION_ANNOUNCEMENTS.started };
    case "RECEIVING":
      return state.inFlight
        ? { inFlight: false, message: GENERATION_ANNOUNCEMENTS.complete }
        : state;
    case "READY":
      return state.inFlight
        ? { inFlight: false, message: GENERATION_ANNOUNCEMENTS.failed }
        : state;
    case "OFFLINE":
      return state;
  }
}

/**
 * Visually hidden live region for the generation lifecycle. It is mounted
 * empty and filled from an effect, so screen readers observe each message as
 * a change to an existing polite region.
 */
function GenerationAnnouncer({ skaldStatus }: { skaldStatus: SkaldStatus }) {
  const [state, observe] = useReducer(announce, {
    inFlight: false,
    message: "",
  });
  useEffect(() => {
    observe(skaldStatus);
  }, [skaldStatus]);
  return (
    <span
      role="status"
      aria-live="polite"
      className="sr-only"
      data-testid="generation-announcer"
    >
      {state.message}
    </span>
  );
}

function MemoryMeter() {
  const { data: settings } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
  });
  const pollIdleMs =
    settings?.ui?.local_models?.poll_idle_ms ??
    LOCAL_MODELS_KNOB_DEFAULTS.poll_idle_ms;
  const pollBusyMs =
    settings?.ui?.local_models?.poll_busy_ms ??
    LOCAL_MODELS_KNOB_DEFAULTS.poll_busy_ms;
  const { data: status } = useQuery<LocalModelsStatus>({
    queryKey: [...LOCAL_MODELS_STATUS_KEY],
    // Busy cadence while a swap is in flight: activation is fire-and-forget
    // and the settings pane (the other busy observer) may be unmounted, so
    // the meter must notice ready/failed flips on its own.
    refetchInterval: (query) => {
      const active = query.state.data?.active;
      const busy = Boolean(active && !active.ready && !active.failed);
      return busy ? pollBusyMs : pollIdleMs;
    },
    // Keep the meter honest while the window is hidden (see useLocalModels).
    refetchIntervalInBackground: true,
  });

  const active = status?.active;
  if (!status || !active || active.failed) return null;

  const entry = status.catalog.find(
    (candidate) =>
      `${status.models_dir}/${candidate.subdir}/${candidate.filename}` ===
      active.gguf_path,
  );
  const installed = status.installed.find(
    (model) => model.path === active.gguf_path,
  );
  // Catalog size_gb is decimal GB; system_ram_gb is GiB (the min_ram_gb
  // unit). Convert before comparing — the ~7.4% gap is a real fill-ratio
  // error at meter scale. Display keeps decimal GB to match the quant list.
  const usedBytes = entry
    ? entry.size_gb * 1e9
    : (installed?.size_bytes ?? 0);
  const usedGib = usedBytes / 2 ** 30;
  const totalGib = status.system_ram_gb;
  const pct = Math.min(100, (usedGib / totalGib) * 100);
  const over = usedGib > totalGib;

  return (
    <div className="field" data-testid="mem-meter">
      <span className="k">memory</span>
      <span className="mem-track">
        <span
          className={`mem-fill ${active.ready ? "" : "loading"} ${over ? "over" : ""}`}
          style={{ width: `${pct.toFixed(1)}%` }}
        />
      </span>
      <span className="k mem-text" data-testid="mem-text">
        {/* A model activated by path outside the catalog/installed scan has
            no known size; the meter still exists while it serves. */}
        {usedBytes ? (usedBytes / 1e9).toFixed(1) : "—"} /{" "}
        {totalGib.toFixed(0)} gb
      </span>
    </div>
  );
}

export function TopBar({
  slot,
  characterName,
  skaldStatus,
  frontierClock,
}: TopBarProps) {
  return (
    <header className="topbar" data-testid="nexus-topbar">
      <div className="topbar-left">
        <span className="wordmark">NEXUS</span>
        <span className="brass-pip" aria-hidden="true" />
        <span className="slot-label" data-testid="text-slot-label">
          SLOT <b>{slot ?? "—"}</b>
          {characterName && (
            <>
              {" · "}
              <em>{characterName}</em>
            </>
          )}
        </span>
      </div>

      <div className="topbar-right">
        {frontierClock && (
          <time
            className="frontier-clock"
            dateTime={frontierClock.instant}
            data-testid="frontier-clock"
          >
            {frontierClock.face}
          </time>
        )}
        <MemoryMeter />
        {skaldStatus === "OFFLINE" && (
          <span className="field">
            <span className="v offline" data-testid="text-skald-status">
              OFFLINE
            </span>
          </span>
        )}
      </div>
      <GenerationAnnouncer skaldStatus={skaldStatus} />
    </header>
  );
}
