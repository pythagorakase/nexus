import { useEffect, useRef } from "react";
import { LocalModelRows } from "nexus-ui";

// Per-quant local-model manager — the "local" provider's rows inside the MODEL
// card. Data-bound: the fetch stub in ds-provider.tsx serves GET
// /api/local-models/status and /download from the real nexus.toml Hermes
// catalog. The component returns bare <li>s, so a <ul className="model-list">
// wrapper is required; that is exactly how SettingsPane mounts it.
//
// Both cells of a card render in ONE page load against ONE React Query cache,
// so they necessarily read the same payload — per-cell scenarios are not
// possible here. The stub's single scenario is therefore tuned to show every
// row state at once: 36b q4_k_m serving, q6_k on disk, q8_0 downloadable, 70b
// q4_k_m mid-download, and the two 70b quants above the 48 gb memory ceiling.

// Cadence is dialled back from the nexus.toml knobs: a still card has no use for
// a 1 s download poll, and a quiet page lets the capture settle.
const STILL_KNOBS = {
  poll_busy_ms: 60_000,
  poll_idle_ms: 60_000,
  download_poll_ms: 60_000,
  delete_arm_ms: 2_800,
};

function Rows({ expand }: { expand: boolean }) {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!expand) return;
    // The accordion's `open` map is internal useState with no prop to seed it,
    // and the families do not exist in the DOM until the status query resolves —
    // so poll briefly and drive the component's own chevron, the same way the
    // ContextMenu preview dispatches a real event rather than faking the open
    // state. Selecting on aria-expanded="false" makes this idempotent: a family
    // that is already open is never toggled shut.
    const openCollapsed = () =>
      ref.current
        ?.querySelectorAll<HTMLButtonElement>(
          '[data-testid^="lm-toggle-"][aria-expanded="false"]',
        )
        .forEach((chevron) => chevron.click());
    const poll = setInterval(openCollapsed, 60);
    const stop = setTimeout(() => clearInterval(poll), 2500);
    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [expand]);

  // The `nexus-shell` ancestor is required, not decoration: alongside its own
  // unscoped `.lm-*` rules the component emits `.caption`, `.btn-soft`, and
  // `.btn-primary`, and nexus-layout.css defines all three ONLY under
  // `.nexus-shell`. A bare <ul> renders the quant labels and the EJECT / APPLY
  // buttons as browser defaults. Same trap the SettingsPane preview documents.
  // The shell's 100vh height and 52px TopBar grid row are overridden locally so
  // the lone list fills the cell.
  return (
    <div
      className="nexus-shell"
      style={{ width: 480, height: "auto", gridTemplateRows: "auto", padding: 16 }}
    >
      <ul className="model-list" ref={ref}>
        <LocalModelRows selected onPickLocal={() => {}} knobs={STILL_KNOBS} />
      </ul>
    </div>
  );
}

// Rest state: one row per family, collapsed. The serving family carries its
// quant summary and a filled radio; the idle one shows neither. The EJECT
// action appears because a model is loaded.
export const Families = () => <Rows expand={false} />;

// Expanded: the per-quant manager. Reading down, the states are the active dot,
// an on-disk quant with its armed-delete trash, a downloadable quant, the
// in-flight download with percentage and progress bar, and the two quants the
// machine has too little memory to load.
export const Quantizations = () => <Rows expand />;
