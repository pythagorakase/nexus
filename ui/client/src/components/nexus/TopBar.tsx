/**
 * TopBar - the 52px operator strip across the top of the NexusLayout.
 *
 * Left: NEXUS wordmark (the single marquee-font element on this surface)
 * plus the slot label. Right: nothing at rest. Per the visual minimalism
 * doctrine the old persistent `SKALD <status>` field is gone - it carried
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
 */
import { useQuery } from "@tanstack/react-query";
import {
  LOCAL_MODELS_KNOB_DEFAULTS,
  LOCAL_MODELS_STATUS_KEY,
} from "@/hooks/useLocalModels";
import type { LocalModelsStatus } from "@/types/localModels";
import type { SettingsPayload } from "@/types/settings";
import type { SkaldStatus } from "@/types/narrative";

interface TopBarProps {
  slot: number | null;
  characterName: string | null;
  skaldStatus: SkaldStatus;
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

export function TopBar({ slot, characterName, skaldStatus }: TopBarProps) {
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
        <MemoryMeter />
        {skaldStatus === "OFFLINE" && (
          <span className="field">
            <span className="v offline" data-testid="text-skald-status">
              OFFLINE
            </span>
          </span>
        )}
      </div>
    </header>
  );
}
