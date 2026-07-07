// Floating hover-audit popover: the fixed-position shell (hoverPanelStyle in
// the prototype's logic block) around EntityAudit. The parent owns the hover
// intent timers; onEnter/onLeave let the panel keep itself alive while the
// pointer is inside it.

import EntityAudit from "./EntityAudit";
import type { EntityAuditVM } from "./types";

export default function HoverAudit({
  ent,
  x,
  y,
  onEnter,
  onLeave,
}: {
  ent: EntityAuditVM | null;
  x: number;
  y: number;
  onEnter: () => void;
  onLeave: () => void;
}) {
  if (!ent) return null;
  return (
    <div
      data-screen-label="Hover audit"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      style={{
        position: "fixed",
        left: x,
        top: y,
        zIndex: 80,
        background: "hsl(var(--popover))",
        border: "1px solid hsl(var(--popover-border))",
        borderRadius: 8,
        padding: 14,
        boxShadow: "0 8px 28px hsl(220 40% 2% / 0.7)",
      }}
    >
      <EntityAudit ent={ent} />
    </div>
  );
}
