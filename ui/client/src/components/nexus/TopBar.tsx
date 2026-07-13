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
  const { data: status } = useQuery<LocalModelsStatus>({
    queryKey: [...LOCAL_MODELS_STATUS_KEY],
    refetchInterval: pollIdleMs,
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
  const usedGb = entry?.size_gb ?? (installed ? installed.size_bytes / 1e9 : 0);
  if (!usedGb) return null;

  const totalGb = status.system_ram_gb;
  const pct = Math.min(100, (usedGb / totalGb) * 100);
  const over = usedGb > totalGb;

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
        {usedGb.toFixed(1)} / {totalGb.toFixed(0)} gb
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
