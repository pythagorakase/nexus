// DevOrreryPage — the Orrery audit dashboard, assembled from the design
// prototype (ui/.design-sync/import/orrery/Orrery Audit Dashboard.dc.html)
// with the mock engine replaced by the live /api/dev/orrery endpoints via
// ./api.ts (fetchers), ./vm.ts (payload -> view-model adapters) and
// @tanstack/react-query.
//
// Deviations from the prototype, and why:
//   - slot picker offers all five save slots (the mock hardcoded 3);
//     footer line is "slot N · <actor_count> actors" (no per-slot lore).
//   - the empty-slot notice is generalized ("No off-screen actors resolve
//     on this slot.") instead of the mock's save_01 copy.
//   - "As-of" only opens the informational per-axis honesty popover; it
//     never changes resolve behavior (the live API has no as-of mode).
//   - windowLabel renders in the tick bar (HealthStrip has no slot for it).
//   - switching slots clears overrides/selection (entity ids are per-slot;
//     stale overrides would be nonsense against another database).
//   - density/magnitudeStyle are constants (comfortable, dial) — no editor.
//   - the root drops the prototype's negative margin (that countered the
//     design-preview frame padding, which the app shell doesn't have).
//   - card target-name hover audits are not wired: ResolutionCardVM carries
//     no hover callback (group headers, on-screen chips and graph nodes
//     cover the hover-audit surface).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CSSProperties,
  MouseEvent as ReactMouseEvent,
  ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

import {
  OrreryApiError,
  fetchCatalog,
  fetchCoverage,
  fetchEntityContext,
  fetchResolve,
  fetchVocab,
} from "./api";
import {
  BAND_LABELS,
  BAND_ORDER,
  NEEDS,
  bandColor,
  buildEntityAudit,
  buildGroups,
  buildInspector,
  priorityTies,
  winnersByBand,
} from "./vm";
import type { GroupBuildCtx } from "./vm";
import type {
  ActorGroupVM,
  CatalogPayload,
  ContextEntity,
  ContextPayload,
  CoveragePayload,
  GhostRowVM,
  InspectorGateRowVM,
  InspectorVM,
  OverrideChipEntry,
  OverridesRequest,
  PressureChipVM,
  ResolvePayload,
  SelectionRef,
  VocabPayload,
} from "./types";
import HealthStrip from "./HealthStrip";
import type { HealthStripProps } from "./HealthStrip";
import HoverAudit from "./HoverAudit";
import InteractionGraph from "./InteractionGraph";
import ResolutionCard from "./ResolutionCard";
import WhatIfDrawer from "./WhatIfDrawer";

// ---------------------------------------------------------------------------
// Constants (the prototype's density/magnitudeStyle editor props, frozen)
// ---------------------------------------------------------------------------

const MAGNITUDE_STYLE: "dial" | "numeric" = "dial";
const PAD = 10; // density: comfortable

const PAGE_CSS = `
@keyframes orr-pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
`;

// Exact axes list from the prototype's logic block (asofAxes).
const ASOF_AXES: { axis: string; glyph: string; color: string; label: string }[] = [
  {
    axis: "Recent events · world time · roster",
    glyph: "✓",
    color: "hsl(var(--chart-5))",
    label: "honest",
  },
  {
    axis: "Single-entity tags",
    glyph: "≈",
    color: "hsl(var(--chart-2))",
    label: "approximate",
  },
  {
    axis: "Pair tags",
    glyph: "≈",
    color: "hsl(var(--chart-2))",
    label: "approx · no clear log",
  },
  {
    axis: "Relationships / trust",
    glyph: "∅",
    color: "hsl(var(--muted-foreground))",
    label: "frozen · unversioned",
  },
  {
    axis: "Position / activity",
    glyph: "∅",
    color: "hsl(var(--muted-foreground))",
    label: "frozen · uninstrumented",
  },
  {
    axis: "Need debt",
    glyph: "✓",
    color: "hsl(var(--chart-5))",
    label: "replayable",
  },
  {
    axis: "Travel · anchors · factions · weather",
    glyph: "∅",
    color: "hsl(var(--muted-foreground))",
    label: "frozen",
  },
];

// ---------------------------------------------------------------------------
// Style helpers (ports of the prototype's chip()/tab()/status maps)
// ---------------------------------------------------------------------------

const chipStyle = (active: boolean, color: string): CSSProperties => ({
  border: "none",
  borderRadius: 4,
  padding: "3px 10px",
  fontSize: 9.5,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  cursor: "pointer",
  background: active ? `hsl(var(--${color}) / 0.18)` : "transparent",
  color: active ? `hsl(var(--${color}))` : "hsl(var(--muted-foreground))",
});

const tabStyle = (active: boolean): CSSProperties => ({
  border: "none",
  borderBottom: `2px solid ${active ? "hsl(var(--primary))" : "transparent"}`,
  background: "transparent",
  padding: "4px 12px 6px",
  fontSize: 10,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  cursor: "pointer",
  color: active ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
});

const railLabelStyle: CSSProperties = {
  fontSize: 9,
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "hsl(var(--muted-foreground))",
};

const statusChipStyle = (
  tone: InspectorVM["statusTone"],
  band: string,
): CSSProperties => {
  const base: CSSProperties = {
    fontSize: 8.5,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    borderRadius: 99,
    padding: "2px 9px",
  };
  switch (tone) {
    case "winner":
      return { ...base, border: `1px solid ${band}`, color: band };
    case "shadowed":
      return {
        ...base,
        border: "1px solid hsl(var(--muted-foreground) / 0.5)",
        color: "hsl(var(--muted-foreground))",
      };
    case "failed":
      return {
        ...base,
        border: "1px solid hsl(var(--destructive) / 0.6)",
        color: "hsl(var(--destructive))",
      };
    case "na":
      return {
        ...base,
        border: "1px solid hsl(var(--muted-foreground) / 0.4)",
        color: "hsl(var(--muted-foreground) / 0.7)",
      };
  }
};

const pressureChipStyle = (selected: boolean, diff: boolean): CSSProperties => ({
  border: `1px solid ${selected ? "hsl(var(--accent))" : "hsl(var(--accent) / 0.55)"}`,
  background: selected
    ? "hsl(var(--accent) / 0.16)"
    : diff
      ? "hsl(var(--accent) / 0.1)"
      : "transparent",
  color: "hsl(var(--accent))",
  borderRadius: 99,
  padding: "3px 11px",
  fontSize: 10,
  letterSpacing: "0.05em",
  cursor: "pointer",
});

// ---------------------------------------------------------------------------
// Small hover-styled building blocks (style-hover="" in the DSL)
// ---------------------------------------------------------------------------

function HoverBtn({
  style,
  hoverStyle,
  onClick,
  title,
  className,
  children,
}: {
  style: CSSProperties;
  hoverStyle: CSSProperties;
  onClick: () => void;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      title={title}
      className={className}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ ...style, ...(hovered ? hoverStyle : {}) }}
    >
      {children}
    </button>
  );
}

function GhostRow({ gh }: { gh: GhostRowVM }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={gh.onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "2px 8px",
        borderRadius: 4,
        cursor: "pointer",
        color: `hsl(var(--muted-foreground) / ${gh.na ? "0.5" : "0.62"})`,
        ...(gh.na
          ? { borderLeft: "2px dotted hsl(var(--muted-foreground) / 0.4)" }
          : {}),
        ...(hovered ? { background: "hsl(var(--muted) / 0.2)" } : {}),
      }}
    >
      <span style={{ width: 14, flex: "none", textAlign: "center", fontSize: 9 }}>
        {gh.glyph}
      </span>
      <span
        className="font-mono"
        style={{
          fontSize: 9.5,
          letterSpacing: "0.08em",
          flex: "none",
          minWidth: 150,
        }}
      >
        {gh.name}
      </span>
      <span
        style={{
          flex: 1,
          fontSize: 11,
          fontStyle: "italic",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {gh.reason}
      </span>
      <span className="font-mono" style={{ fontSize: 9.5, flex: "none" }}>
        {gh.evidence}
      </span>
    </div>
  );
}

function PressureChip({ pr }: { pr: PressureChipVM }) {
  return (
    <button
      type="button"
      onClick={pr.onSelect}
      title={pr.title}
      className="font-mono"
      style={pressureChipStyle(pr.selected, pr.diff)}
    >
      ⇢ {pr.label}
    </button>
  );
}

function StreamGroup({
  g,
  selectedActor,
  showFailedHint,
  onHoverName,
  onHoverOut,
}: {
  g: ActorGroupVM;
  selectedActor: number | null;
  showFailedHint: boolean;
  onHoverName: (id: number) => (e: ReactMouseEvent) => void;
  onHoverOut: () => void;
}) {
  const [headHover, setHeadHover] = useState(false);
  const borderColor = g.gap
    ? "hsl(var(--destructive) / 0.45)"
    : selectedActor === g.id
      ? "hsl(var(--primary) / 0.5)"
      : "hsl(var(--border))";
  return (
    <div
      id={g.domId}
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        background: "hsl(var(--card) / 0.45)",
      }}
    >
      <div
        onClick={g.onToggle}
        onMouseEnter={() => setHeadHover(true)}
        onMouseLeave={() => setHeadHover(false)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "8px 12px",
          cursor: "pointer",
          ...(headHover ? { background: "hsl(var(--muted) / 0.25)" } : {}),
        }}
      >
        <span
          style={{
            fontSize: 9,
            color: "hsl(var(--muted-foreground))",
            width: 10,
            flex: "none",
          }}
        >
          {g.open ? "▾" : "▸"}
        </span>
        <span
          className="font-mono"
          style={{
            width: 30,
            height: 30,
            borderRadius: 99,
            border: `1.5px solid ${g.ringColor}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            color: "hsl(var(--foreground) / 0.85)",
            flex: "none",
            background: "hsl(var(--card))",
          }}
        >
          {g.initials}
        </span>
        <span
          onMouseEnter={onHoverName(g.id)}
          onMouseLeave={onHoverOut}
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "hsl(var(--foreground))",
            textDecoration: "underline dotted hsl(var(--primary) / 0.5)",
            textUnderlineOffset: 3,
            cursor: "default",
          }}
        >
          {g.name}
        </span>
        <span
          className="font-mono"
          style={{
            fontSize: 9.5,
            letterSpacing: "0.08em",
            color: "hsl(var(--muted-foreground))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 99,
            padding: "1px 8px",
            flex: "none",
          }}
        >
          {g.placeName}
        </span>
        {g.diff && (
          <span
            title="Outcome changed vs pre-override tick"
            style={{
              width: 7,
              height: 7,
              borderRadius: 99,
              background: "hsl(var(--accent))",
              boxShadow: "0 0 7px hsl(var(--accent))",
              flex: "none",
            }}
          />
        )}
        <div style={{ flex: 1 }} />
        {g.gap && (
          <span
            className="font-mono"
            style={{
              fontSize: 9,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "hsl(var(--destructive))",
              border: "1px solid hsl(var(--destructive) / 0.6)",
              borderRadius: 99,
              padding: "2px 8px",
            }}
          >
            coverage gap
          </span>
        )}
        <div style={{ display: "flex", gap: 4, flex: "none" }}>
          {g.bandDots.map((bd, i) => (
            <span
              key={`${bd.title}:${i}`}
              title={bd.title}
              style={{
                width: 7,
                height: 7,
                borderRadius: 2,
                background: bd.color,
              }}
            />
          ))}
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: 9.5,
            color: "hsl(var(--muted-foreground))",
            flex: "none",
          }}
        >
          {g.activityLine}
        </span>
      </div>
      {g.open && (
        <div
          style={{
            padding: "2px 12px 12px 32px",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {g.gap && (
            <div
              style={{
                border: "1px dashed hsl(var(--destructive) / 0.5)",
                borderRadius: 6,
                padding: "9px 12px",
                fontSize: 12,
                fontStyle: "italic",
                color: "hsl(var(--muted-foreground))",
              }}
            >
              No package fires for this actor this tick — every gate refuses.{" "}
              {showFailedHint
                ? "Toggle “show gate-failed” to see every refusal."
                : ""}
            </div>
          )}
          {g.cards.map((card) => (
            <ResolutionCard
              key={card.key}
              card={card}
              magnitudeStyle={MAGNITUDE_STYLE}
            />
          ))}
          {g.pressures.length > 0 && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 6,
                alignItems: "center",
              }}
            >
              {g.pressures.map((pr) => (
                <PressureChip key={pr.key} pr={pr} />
              ))}
            </div>
          )}
          {g.ghosts.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 2,
                marginTop: 2,
              }}
            >
              {g.ghosts.map((gh) => (
                <GhostRow key={gh.key} gh={gh} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inspector rendering (the template's right column, fed by InspectorVM)
// ---------------------------------------------------------------------------

function gateRowProseStyle(gr: InspectorGateRowVM): CSSProperties {
  if (gr.isOp) {
    return {
      flex: 1,
      fontSize: 9.5,
      letterSpacing: "0.2em",
      ...(gr.emphasized
        ? { fontWeight: 700, color: "hsl(var(--foreground) / 0.9)" }
        : { color: "hsl(var(--muted-foreground) / 0.75)" }),
    };
  }
  return {
    flex: 1,
    fontSize: 12,
    ...(gr.emphasized
      ? { fontWeight: 700, color: "hsl(var(--foreground))" }
      : gr.muted
        ? { color: "hsl(var(--muted-foreground))" }
        : { color: "hsl(var(--foreground) / 0.85)" }),
  };
}

function InspectorPane({ insp }: { insp: InspectorVM }) {
  const sectionLabel: CSSProperties = {
    fontSize: 9.5,
    letterSpacing: "0.2em",
    textTransform: "uppercase",
    color: "hsl(var(--muted-foreground))",
  };
  const eventChip: CSSProperties = {
    fontSize: 9.5,
    border: `1px solid ${insp.bandColor}`,
    color: insp.bandColor,
    borderRadius: 99,
    padding: "1px 8px",
  };
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "14px 16px 12px",
          borderBottom: "1px solid hsl(var(--border))",
          borderLeft: `3px solid ${insp.bandColor}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            className="font-mono"
            style={{ fontSize: 13, letterSpacing: "0.12em" }}
          >
            {insp.name}
          </span>
          <span
            className="font-mono"
            style={{ fontSize: 9.5, color: "hsl(var(--muted-foreground))" }}
          >
            pri {insp.priority}
          </span>
          {insp.tie && (
            <span
              title={insp.tieTitle}
              className="font-mono"
              style={{
                fontSize: 9,
                letterSpacing: "0.08em",
                border: "1px solid hsl(var(--chart-5) / 0.7)",
                color: "hsl(var(--chart-5))",
                borderRadius: 99,
                padding: "1px 7px",
                cursor: "help",
              }}
            >
              tie · tuple order
            </span>
          )}
          <div style={{ flex: 1 }} />
          <span
            className="font-mono"
            style={statusChipStyle(insp.statusTone, insp.bandColor)}
          >
            {insp.statusLabel}
          </span>
        </div>
        <div
          style={{
            marginTop: 6,
            fontSize: 12,
            color: "hsl(var(--muted-foreground))",
          }}
        >
          {insp.bindingLine}
        </div>
        <div
          style={{
            marginTop: 4,
            fontSize: 12,
            fontStyle: "italic",
            color: "hsl(var(--muted-foreground) / 0.85)",
          }}
        >
          {insp.blurb}
        </div>
      </div>

      {insp.isNA && (
        <div
          style={{
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <span className="font-mono" style={sectionLabel}>
            Not applicable
          </span>
          <span
            style={{
              fontSize: 12.5,
              fontStyle: "italic",
              color: "hsl(var(--muted-foreground))",
            }}
          >
            No TARGET is bound in this actor's stacks — this two-party template
            was never composed, so nothing was evaluated. Not applicable is not
            a refusal: no gate ran, no predicate failed.
          </span>
        </div>
      )}

      {!insp.isNA && (
        <>
          <div
            style={{
              padding: "12px 16px",
              display: "flex",
              flexDirection: "column",
              gap: 3,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 4,
              }}
            >
              <span className="font-mono" style={sectionLabel}>
                Gate
              </span>
              <span
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  borderRadius: 99,
                  padding: "1px 8px",
                  border: `1px solid ${
                    insp.gatePassed
                      ? "hsl(var(--chart-5) / 0.6)"
                      : "hsl(var(--destructive) / 0.6)"
                  }`,
                  color: insp.gatePassed
                    ? "hsl(var(--chart-5))"
                    : "hsl(var(--destructive))",
                }}
              >
                {insp.gatePassed ? "pass" : "refused"}
              </span>
            </div>
            {insp.gateRows.map((gr, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 7,
                  padding: gr.isOp
                    ? `3px 4px 1px ${4 + gr.depth * 15}px`
                    : `2px 4px 2px ${4 + gr.depth * 15}px`,
                  borderRadius: 4,
                  ...(gr.highlighted
                    ? {
                        background: "hsl(var(--accent) / 0.14)",
                        outline: "1px dotted hsl(var(--accent) / 0.7)",
                      }
                    : {}),
                }}
              >
                <span
                  style={{
                    width: 15,
                    flex: "none",
                    textAlign: "center",
                    fontSize: gr.isOp ? 9 : 10,
                    color: gr.glyphColor,
                  }}
                >
                  {gr.glyph}
                </span>
                <span style={gateRowProseStyle(gr)}>{gr.prose}</span>
                <span
                  className="font-mono"
                  style={{
                    fontSize: 9.5,
                    color: gr.evidenceHot
                      ? "hsl(var(--destructive))"
                      : "hsl(var(--muted-foreground))",
                    flex: "none",
                    textAlign: "right",
                  }}
                >
                  {gr.evidence}
                </span>
              </div>
            ))}
          </div>

          <div
            style={{
              padding: "4px 16px 12px",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <span
              className="font-mono"
              style={{ ...sectionLabel, marginBottom: 2 }}
            >
              Branch ladder — authored order
            </span>
            {insp.branches.map((br) => (
              <div
                key={br.idx}
                style={{
                  padding: "5px 8px",
                  borderRadius: 5,
                  borderLeft: `2px solid ${br.selected ? insp.bandColor : "transparent"}`,
                  ...(br.selected
                    ? { background: "hsl(var(--muted) / 0.22)" }
                    : {}),
                  ...(br.unevaluated ? { opacity: 0.42 } : {}),
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span
                    className="font-mono"
                    style={{
                      fontSize: 9,
                      color: "hsl(var(--muted-foreground))",
                      flex: "none",
                    }}
                  >
                    {br.idx}
                  </span>
                  <span
                    style={{
                      fontSize: 12,
                      flex: 1,
                      ...(br.selected
                        ? { fontWeight: 650 }
                        : { color: "hsl(var(--muted-foreground))" }),
                    }}
                  >
                    {br.label}
                  </span>
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, color: br.magColor, flex: "none" }}
                  >
                    {br.mag}
                  </span>
                </div>
                {br.note && (
                  <div
                    style={{
                      margin: "3px 0 0 17px",
                      fontSize: 10.5,
                      color: "hsl(var(--muted-foreground))",
                      display: "flex",
                      gap: 6,
                      alignItems: "baseline",
                    }}
                  >
                    <span style={{ flex: "none" }}>{br.noteGlyph}</span>
                    <span style={{ fontStyle: "italic" }}>{br.note}</span>
                  </div>
                )}
              </div>
            ))}
          </div>

          {insp.fired && (
            <div
              style={{
                padding: "4px 16px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 8,
                borderTop: "1px solid hsl(var(--border))",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginTop: 10,
                }}
              >
                <span className="font-mono" style={sectionLabel}>
                  Resolution
                </span>
                {insp.event && (
                  <span className="font-mono" style={eventChip}>
                    {insp.event}
                  </span>
                )}
                {insp.signalEvent && (
                  <span
                    className="font-mono"
                    title="signal event — emitted alongside the primary event"
                    style={eventChip}
                  >
                    signal · {insp.signalEvent}
                  </span>
                )}
                <div style={{ flex: 1 }} />
                <span
                  className="font-mono"
                  style={{ fontSize: 10, color: "hsl(var(--muted-foreground))" }}
                >
                  mag {insp.mag}
                </span>
              </div>
              {insp.isPressure && (
                <div
                  style={{
                    border: "1px dashed hsl(var(--accent) / 0.5)",
                    borderRadius: 6,
                    padding: "8px 10px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}
                >
                  <span
                    className="font-mono"
                    style={{
                      fontSize: 8.5,
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      color: "hsl(var(--accent))",
                    }}
                  >
                    Scene pressure — prompt-only, no state mutation
                  </span>
                  <span
                    style={{
                      fontSize: 11.5,
                      fontStyle: "italic",
                      color: "hsl(var(--muted-foreground))",
                    }}
                  >
                    {insp.pressureStub}
                  </span>
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {insp.deltaRows.map((dr) => (
                  <div
                    key={dr.k}
                    style={{
                      display: "flex",
                      gap: 10,
                      fontSize: 10.5,
                      alignItems: "baseline",
                    }}
                  >
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 9,
                        color: "hsl(var(--muted-foreground))",
                        flex: "none",
                        minWidth: 150,
                        textAlign: "right",
                      }}
                    >
                      {dr.k}
                    </span>
                    <span
                      className="font-mono"
                      style={{ fontSize: 10, color: "hsl(var(--chart-5))" }}
                    >
                      {dr.v}
                    </span>
                  </div>
                ))}
              </div>
              <div
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  color: "hsl(var(--muted-foreground) / 0.6)",
                  letterSpacing: "0.04em",
                }}
              >
                {insp.bindingHash}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overrides merging
// ---------------------------------------------------------------------------

function mergeOverrides(chips: OverrideChipEntry[]): OverridesRequest | null {
  if (chips.length === 0) return null;
  const req: OverridesRequest = {
    tags: [],
    pair_tags: [],
    needs: [],
    locations: [],
    events: [],
  };
  for (const chip of chips) {
    req.tags.push(...(chip.patch.tags ?? []));
    req.pair_tags.push(...(chip.patch.pair_tags ?? []));
    req.needs.push(...(chip.patch.needs ?? []));
    req.locations.push(...(chip.patch.locations ?? []));
    req.events.push(...(chip.patch.events ?? []));
  }
  return req;
}

const shortBandLabel = (band: string): string =>
  (BAND_LABELS[band] ?? band)
    .replace(" / Constraint", "")
    .replace(" Maintenance", "")
    .replace("Anchored ", "")
    .replace(" / Identity", "");

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DevOrreryPage() {
  // ---- state ---------------------------------------------------------------
  const [slot, setSlot] = useState(2);
  const [anchor, setAnchor] = useState<number | null>(null); // null = head
  const [head, setHead] = useState<number | null>(null);
  const [mode, setMode] = useState<"current" | "whatif">("current");
  const [asofOpen, setAsofOpen] = useState(false);
  const [overrides, setOverrides] = useState<OverrideChipEntry[]>([]);
  const [selection, setSelection] = useState<SelectionRef | null>(null);
  const [hoverTag, setHoverTag] = useState<string | null>(null);
  const [fTwoParty, setFTwoParty] = useState(false);
  const [fFamily, setFFamily] = useState<string | null>(null);
  const [famOpen, setFamOpen] = useState(false);
  const [fEvent, setFEvent] = useState("none");
  const [fFailed, setFFailed] = useState(false);
  const [fNA, setFNA] = useState(false);
  const [groupOpen, setGroupOpen] = useState<Record<number, boolean>>({});
  const [shadowOpen, setShadowOpen] = useState<Record<string, boolean>>({});
  const [centerTab, setCenterTab] = useState<"stream" | "graph">("stream");
  const [healthOpen, setHealthOpen] = useState(false);
  const [whatifOpen, setWhatifOpen] = useState(false);
  const [hoverEnt, setHoverEnt] = useState<number | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });
  const hoverTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);

  // The prototype's --orr-z CSS zoom rig is deliberately NOT ported: CSS
  // `zoom` corrupts getBoundingClientRect coordinates, which Radix/floating-ui
  // portals (Select, Popover, Command) use for positioning — dropdowns land
  // off-viewport on wide monitors. The flex layout scales fine without it.

  useEffect(
    () => () => {
      if (hoverTimer.current != null) window.clearTimeout(hoverTimer.current);
      if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
    },
    [],
  );

  // ---- queries ---------------------------------------------------------------
  const overridesReq = useMemo(() => mergeOverrides(overrides), [overrides]);
  const overridesJson = overridesReq ? JSON.stringify(overridesReq) : "";

  const resolveQ = useQuery<ResolvePayload, Error>({
    queryKey: ["orrery", "resolve", slot, anchor, overridesJson],
    queryFn: () =>
      fetchResolve({ slot, anchorChunkId: anchor, overrides: overridesReq }),
    placeholderData: (prev) => prev,
  });
  const catalogQ = useQuery<CatalogPayload, Error>({
    queryKey: ["orrery", "catalog"],
    queryFn: fetchCatalog,
  });
  const coverageQ = useQuery<CoveragePayload, Error>({
    queryKey: ["orrery", "coverage", slot],
    queryFn: () => fetchCoverage({ slot }),
  });
  const vocabQ = useQuery<VocabPayload, Error>({
    queryKey: ["orrery", "vocab", slot],
    queryFn: () => fetchVocab(slot),
  });

  const payload = resolveQ.data;
  const catalog = catalogQ.data;
  const coverage = coverageQ.data;

  // Head anchor: the first at-head resolve fixes the stepper's upper bound.
  useEffect(() => {
    if (
      anchor === null &&
      payload &&
      !resolveQ.isPlaceholderData &&
      payload.anchor_chunk_id != null
    ) {
      setHead(payload.anchor_chunk_id);
    }
  }, [anchor, payload, resolveQ.isPlaceholderData]);

  // ---- hover intent (180ms in, 200ms out — prototype's hoverIn/onHoverOut) --
  const hoverIntent = useCallback((id: number, e: ReactMouseEvent) => {
    if (hoverTimer.current != null) window.clearTimeout(hoverTimer.current);
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(r.left, (window.innerWidth || 1440) - 340);
    const y = Math.min(r.bottom + 6, (window.innerHeight || 900) - 440);
    hoverTimer.current = window.setTimeout(() => {
      setHoverEnt(id);
      setHoverPos({ x, y });
    }, 180);
  }, []);
  const hoverOut = useCallback(() => {
    if (hoverTimer.current != null) window.clearTimeout(hoverTimer.current);
    closeTimer.current = window.setTimeout(() => setHoverEnt(null), 200);
  }, []);
  const hoverPanelEnter = useCallback(() => {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
  }, []);
  const hoverNameHandler = useCallback(
    (id: number) => (e: ReactMouseEvent) => hoverIntent(id, e),
    [hoverIntent],
  );

  const hoverCtxQ = useQuery<ContextPayload, Error>({
    queryKey: ["orrery", "context", slot, hoverEnt],
    queryFn: () =>
      fetchEntityContext({
        slot,
        entityIds: [hoverEnt as number],
        anchorChunkId: anchor,
      }),
    enabled: hoverEnt != null,
  });

  // Drawer bulk context: every entity the payload names, fetched on open.
  const drawerEntities = useMemo(() => {
    // Actors plus the characters their stacks bind — not every named
    // entity (payload.entity_names also carries places and factions).
    if (!payload) return [] as { id: number; name: string }[];
    const m = new Map<number, string>();
    const nameOf = (id: number) =>
      payload.entity_names[String(id)] ?? `entity ${id}`;
    for (const g of payload.actors) {
      m.set(g.actor_entity_id, g.actor_name);
      for (const stack of [...g.two_party_stacks, ...g.scene_pressure_stacks]) {
        const target = stack.bindings.target;
        if (target != null && !m.has(target)) m.set(target, nameOf(target));
      }
    }
    return Array.from(m, ([id, name]) => ({ id, name })).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
  }, [payload]);
  const drawerIdsKey = drawerEntities.map((e) => e.id).join(",");
  const drawerCtxQ = useQuery<ContextPayload, Error>({
    queryKey: ["orrery", "context", slot, "drawer", drawerIdsKey],
    queryFn: () =>
      fetchEntityContext({
        slot,
        entityIds: drawerEntities.map((e) => e.id),
        anchorChunkId: anchor,
      }),
    enabled: whatifOpen && drawerEntities.length > 0,
  });
  const entityContext = useCallback(
    (id: number): ContextEntity | undefined =>
      drawerCtxQ.data?.entities.find((e) => e.entity_id === id) ??
      hoverCtxQ.data?.entities.find((e) => e.entity_id === id),
    [drawerCtxQ.data, hoverCtxQ.data],
  );

  // ---- catalog-derived lookups ------------------------------------------------
  const blurbMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const band of catalog?.drive_bands ?? [])
      for (const t of band.templates) m.set(t.template_id, t.blurb);
    return m;
  }, [catalog]);
  const blurbFor = useCallback(
    (tpl: string) => blurbMap.get(tpl) ?? "",
    [blurbMap],
  );
  const branchMap = useMemo(() => {
    const m = new Map<string, { label: string; magnitude: number }[]>();
    for (const band of catalog?.drive_bands ?? [])
      for (const t of band.templates)
        m.set(
          t.template_id,
          t.branches.map((b) => ({ label: b.label, magnitude: b.magnitude })),
        );
    return m;
  }, [catalog]);
  const branchesFor = useCallback(
    (tpl: string) => branchMap.get(tpl) ?? [],
    [branchMap],
  );
  const ties = useMemo(
    () => priorityTies(catalog?.priority_ties ?? []),
    [catalog],
  );
  const familyEntries = useMemo(
    () => Object.entries(catalog?.tag_families ?? {}),
    [catalog],
  );
  const eventOptions = useMemo(
    () =>
      Object.entries(catalog?.event_map ?? {})
        .filter(
          ([, v]) => v.consumed_by_gate.length + v.consumed_by_branch.length > 0,
        )
        .map(([k]) => k)
        .sort(),
    [catalog],
  );

  const familyMembers = fFamily
    ? (catalog?.tag_families[fFamily]?.members ?? null)
    : null;
  const eventLens = fEvent === "none" ? null : fEvent;

  // ---- groups -------------------------------------------------------------------
  const groups: ActorGroupVM[] = useMemo(() => {
    if (!payload) return [];
    const ctx: GroupBuildCtx = {
      selectedKey: selection?.key ?? null,
      familyMembers,
      eventLens,
      magnitudeStyle: MAGNITUDE_STYLE,
      pad: PAD,
      ties,
      shadowOpen,
      select: (sel) => setSelection(sel),
      toggleShadow: (key) =>
        setShadowOpen((prev) => ({ ...prev, [key]: !prev[key] })),
      showTwoPartyOnly: fTwoParty,
      showFailed: fFailed,
      showNA: fNA,
      groupOpen,
      toggleGroup: (id) =>
        setGroupOpen((prev) => ({ ...prev, [id]: prev[id] === false })),
    };
    return buildGroups(payload, ctx);
  }, [
    payload,
    selection,
    familyMembers,
    eventLens,
    ties,
    shadowOpen,
    fTwoParty,
    fFailed,
    fNA,
    groupOpen,
  ]);

  // ---- inspector -------------------------------------------------------------
  const inspector = useMemo(
    () =>
      payload && selection
        ? buildInspector(payload, selection, {
            hoverTag,
            blurbFor,
            branchesFor,
            ties,
          })
        : null,
    [payload, selection, hoverTag, blurbFor, branchesFor, ties],
  );

  // ---- rail / summary ----------------------------------------------------------
  const bandCounts = useMemo(
    () => (payload ? winnersByBand(payload) : null),
    [payload],
  );
  const totalWinners = bandCounts
    ? Object.values(bandCounts).reduce((a, b) => a + b, 0)
    : 0;
  const scenePressureCount = groups.reduce((a, g) => a + g.pressures.length, 0);
  const streamSummary = payload
    ? `${payload.actors.length} actors · ${totalWinners} winners · ${
        payload.need_pressures.length + scenePressureCount
      } pressures`
    : "";
  const displayAnchor =
    anchor ??
    head ??
    (payload && !resolveQ.isPlaceholderData ? payload.anchor_chunk_id : null);
  const chunkStr =
    displayAnchor != null ? String(displayAnchor).padStart(4, "0") : "····";
  const worldTimeStr = payload
    ? `${payload.world_time ?? "—"} · ${payload.time_of_day} · ${payload.weather}`
    : "…";
  const windowLabel =
    payload && payload.anchor_chunk_id != null
      ? `${payload.anchor_chunk_id - payload.window_chunks + 1} → ${payload.anchor_chunk_id}`
      : "—";
  const footerLine = payload
    ? `slot ${slot} · ${payload.actor_count} actors`
    : `slot ${slot}`;

  // ---- on-screen chips + need-pressure chips ---------------------------------
  const onscreenChips = useMemo(() => {
    if (!payload) return [] as { id: number; name: string }[];
    const offIds = new Set(payload.actors.map((g) => g.actor_entity_id));
    const m = new Map<number, string>();
    for (const g of payload.actors) {
      for (const stack of g.scene_pressure_stacks) {
        const target = stack.bindings.target ?? null;
        if (target == null || offIds.has(target) || m.has(target)) continue;
        m.set(
          target,
          stack.binding_names.target ??
            payload.entity_names[String(target)] ??
            String(target),
        );
      }
    }
    return Array.from(m, ([id, name]) => ({ id, name }));
  }, [payload]);

  const needPressureChips = useMemo(() => {
    if (!payload) return [] as { key: string; label: string; title: string }[];
    return payload.need_pressures.map((np) => {
      const target =
        np.bindings["actor"] ?? Object.values(np.bindings)[0] ?? null;
      const name =
        target != null
          ? (payload.entity_names[String(target)] ?? String(target))
          : "—";
      return {
        key: `${np.template_id}:${np.binding_hash}`,
        label: `${np.template_id} → ${name} · ${np.magnitude.toFixed(2)}`,
        title: `pseudo-template · priority ${np.priority} · ${np.pressure_stub} — outside the catalog; included explicitly`,
      };
    });
  }, [payload]);

  // ---- health strip ---------------------------------------------------------------
  const jumpToGroup = useCallback((actorId: number) => {
    setCenterTab("stream");
    setGroupOpen((prev) => ({ ...prev, [actorId]: true }));
    window.setTimeout(() => {
      const elC = document.getElementById("orr-stream");
      const elG = document.getElementById(`group-${actorId}`);
      if (elC && elG) elC.scrollTop = elG.offsetTop - elC.offsetTop - 8;
    }, 60);
  }, []);

  const health: HealthStripProps = useMemo(() => {
    const bands = BAND_ORDER.map((b) => ({
      name: shortBandLabel(b),
      color: bandColor(b),
      count: bandCounts?.[b] ?? 0,
      pct: totalWinners
        ? `${Math.round(((bandCounts?.[b] ?? 0) / totalWinners) * 100)}%`
        : "0%",
    }));
    const gaps = groups
      .filter((g) => g.gap)
      .map((g) => ({ name: g.name, onJump: () => jumpToGroup(g.id) }));
    const wonEntries = Object.entries(coverage?.templates ?? {})
      .map(([id, t]) => ({ id, won: t.won }))
      .filter((t) => t.won > 0)
      .sort((a, b) => b.won - a.won);
    const totalWon = wonEntries.reduce((a, t) => a + t.won, 0);
    const dominant = wonEntries.slice(0, 3).map((t) => ({
      id: t.id,
      share: totalWon ? `${Math.round((t.won / totalWon) * 100)}%` : "0%",
    }));
    const neverWin = (coverage?.never_fired ?? []).map((id) => ({ id }));
    const deadArms = Object.entries(coverage?.dead_gate_arms ?? {}).map(
      ([event, v]) => ({
        event,
        consumers: [...v.consumed_by_gate, ...v.consumed_by_branch].join(", "),
      }),
    );
    const dataQuality: { text: string; color: string }[] = [];
    for (const row of coverage?.data_quality.null_world_time_bestowals ?? []) {
      dataQuality.push({
        text: `${row.bestowal_table} (${row.source_kind}): ${row.null_world_time_rows}/${row.active_rows} active rows have NULL world-time`,
        color: "hsl(var(--destructive))",
      });
    }
    for (const row of coverage?.data_quality.wall_clock_epochs ?? []) {
      dataQuality.push({
        text: `${row.bestowal_table}: ${row.rows} rows share wall-clock ${row.wall_clock_instant} across ${row.distinct_world_times} world-times`,
        color: "hsl(var(--chart-2))",
      });
    }
    return {
      open: healthOpen,
      onToggle: () => setHealthOpen((v) => !v),
      bands,
      gaps,
      dominant,
      neverWin,
      deadArms,
      dataQuality,
      warnCount: coverage
        ? String(dataQuality.length + deadArms.length + gaps.length)
        : "—",
    };
  }, [bandCounts, totalWinners, groups, coverage, healthOpen, jumpToGroup]);

  const deadArmConsumers = useMemo(() => {
    if (!eventLens || !coverage) return [] as string[];
    const arm = coverage.dead_gate_arms[eventLens];
    return arm ? [...arm.consumed_by_gate, ...arm.consumed_by_branch] : [];
  }, [eventLens, coverage]);

  // ---- hover audit VM ----------------------------------------------------------
  const hoverVM = useMemo(() => {
    if (hoverEnt == null || !payload) return null;
    const ent = hoverCtxQ.data?.entities.find((e) => e.entity_id === hoverEnt);
    if (!ent) return null;
    const offScreen = payload.actors.some(
      (g) => g.actor_entity_id === hoverEnt,
    );
    return buildEntityAudit(ent, !offScreen, {
      onTagEnter: (tag) => setHoverTag(tag),
      onTagLeave: () => setHoverTag(null),
    });
  }, [hoverEnt, payload, hoverCtxQ.data]);

  // ---- handlers -----------------------------------------------------------------
  const onSlotChange = (v: string) => {
    setSlot(Number(v));
    setAnchor(null);
    setHead(null);
    setSelection(null);
    setOverrides([]);
    setGroupOpen({});
    setShadowOpen({});
    setHoverEnt(null);
    setMode("current");
  };
  const stepTo = (next: number) => {
    if (head == null) return;
    const clamped = Math.max(1, Math.min(head, next));
    setAnchor(clamped === head ? null : clamped);
    setSelection(null);
  };
  const onStepBack = () => {
    const cur = anchor ?? head;
    if (cur != null) stepTo(cur - 1);
  };
  const onStepFwd = () => {
    const cur = anchor ?? head;
    if (cur != null) stepTo(cur + 1);
  };
  const applyOverride = (chip: OverrideChipEntry) => {
    setOverrides((prev) => [...prev, chip]);
    setMode("whatif");
  };
  const removeOverride = (idx: number) => {
    setOverrides((prev) => prev.filter((_, j) => j !== idx));
  };

  // ---- error states (loud, not graceful) ---------------------------------------
  const fatal =
    resolveQ.error ??
    catalogQ.error ??
    coverageQ.error ??
    vocabQ.error ??
    drawerCtxQ.error ??
    hoverCtxQ.error ??
    null;

  const rootStyle: CSSProperties = {
    height: "100vh",
    minWidth: 1080,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    position: "relative",
  };

  if (fatal) {
    const is404 = fatal instanceof OrreryApiError && fatal.status === 404;
    return (
      <div
        className="dark bg-background text-foreground font-sans"
        style={rootStyle}
      >
        <style>{PAGE_CSS}</style>
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 40,
          }}
        >
          <div
            style={{
              maxWidth: 520,
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {is404 ? (
              <>
                <span
                  className="font-mono"
                  style={{
                    fontSize: 10,
                    letterSpacing: "0.22em",
                    textTransform: "uppercase",
                    color: "hsl(var(--destructive))",
                  }}
                >
                  Dashboard router is off
                </span>
                <span
                  style={{ fontSize: 13.5, color: "hsl(var(--foreground))" }}
                >
                  Flip{" "}
                  <code className="font-mono">
                    [orrery.dashboard] enabled = true
                  </code>{" "}
                  in nexus.toml and restart the gateway.
                </span>
              </>
            ) : (
              <span
                className="font-mono"
                style={{ fontSize: 13, color: "hsl(var(--destructive))" }}
              >
                {fatal.message}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  const showEmptySlot = !!payload && payload.actors.length === 0;
  const showStream = !!payload && !showEmptySlot && centerTab === "stream";
  const showGraph = !!payload && !showEmptySlot && centerTab === "graph";
  const sandboxFrame = mode === "whatif" && overrides.length > 0;

  const stepBtnStyle: CSSProperties = {
    width: 24,
    height: 24,
    border: "1px solid hsl(var(--border))",
    borderRadius: 4,
    background: "transparent",
    color: "hsl(var(--muted-foreground))",
    cursor: "pointer",
    fontSize: 12,
    lineHeight: 1,
  };
  const stepBtnHover: CSSProperties = {
    borderColor: "hsl(var(--primary))",
    color: "hsl(var(--foreground))",
  };

  return (
    <div
      className="dark bg-background text-foreground font-sans"
      style={rootStyle}
    >
      <style>{PAGE_CSS}</style>

      {/* ═══════════════ TICK BAR ═══════════════ */}
      <div
        className="bg-sidebar"
        style={{
          height: 46,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 14px",
          borderBottom: "1px solid hsl(var(--border))",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 8,
            flex: "none",
          }}
        >
          <span
            className="font-display"
            style={{
              fontSize: 17,
              letterSpacing: "0.06em",
              color: "hsl(var(--primary))",
            }}
          >
            ORRERY
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: 9,
              letterSpacing: "0.22em",
              color: "hsl(var(--muted-foreground))",
              textTransform: "uppercase",
            }}
          >
            Audit
          </span>
        </div>
        <div
          style={{
            width: 1,
            height: 20,
            background: "hsl(var(--border))",
            flex: "none",
          }}
        />
        <Select value={String(slot)} onValueChange={onSlotChange}>
          <SelectTrigger style={{ height: 28, width: 118, fontSize: 11 }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[1, 2, 3, 4, 5].map((n) => (
              <SelectItem key={n} value={String(n)}>
                save_{String(n).padStart(2, "0")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div
          style={{ display: "flex", alignItems: "center", gap: 6, flex: "none" }}
        >
          <HoverBtn
            title="Previous chunk"
            onClick={onStepBack}
            style={stepBtnStyle}
            hoverStyle={stepBtnHover}
          >
            −
          </HoverBtn>
          <span
            className="font-mono"
            style={{
              fontSize: 12,
              letterSpacing: "0.08em",
              minWidth: 88,
              textAlign: "center",
            }}
          >
            chunk {chunkStr}
          </span>
          <HoverBtn
            title="Next chunk"
            onClick={onStepFwd}
            style={stepBtnStyle}
            hoverStyle={stepBtnHover}
          >
            +
          </HoverBtn>
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: 10.5,
            letterSpacing: "0.08em",
            color: "hsl(var(--muted-foreground))",
            flex: "none",
          }}
        >
          {worldTimeStr}
        </span>
        <span
          className="font-mono"
          style={{
            fontSize: 9,
            letterSpacing: "0.1em",
            color: "hsl(var(--muted-foreground))",
            flex: "none",
          }}
        >
          window {windowLabel}
        </span>
        <div style={{ flex: 1 }} />
        {resolveQ.isFetching && (
          <span
            className="font-mono"
            style={{
              fontSize: 9.5,
              letterSpacing: "0.18em",
              color: "hsl(var(--accent))",
              animation: "orr-pulse 0.9s infinite",
              textTransform: "uppercase",
            }}
          >
            resolving
          </span>
        )}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 2,
            border: "1px solid hsl(var(--border))",
            borderRadius: 6,
            padding: 2,
            flex: "none",
          }}
        >
          <button
            type="button"
            className="font-mono"
            style={chipStyle(mode === "current", "primary")}
            onClick={() => {
              setMode("current");
              setWhatifOpen(false);
            }}
          >
            Current
          </button>
          <button
            type="button"
            className="font-mono"
            style={chipStyle(mode === "whatif", "accent")}
            onClick={() => {
              setMode("whatif");
              setWhatifOpen(true);
            }}
          >
            What-if
          </button>
          <Popover open={asofOpen} onOpenChange={setAsofOpen}>
            <PopoverTrigger
              className="font-mono"
              style={chipStyle(asofOpen, "chart-5")}
            >
              As-of
            </PopoverTrigger>
            <PopoverContent align="end">
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 7,
                  minWidth: 250,
                }}
              >
                <div
                  className="font-mono"
                  style={{
                    fontSize: 9.5,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    color: "hsl(var(--muted-foreground))",
                  }}
                >
                  Per-axis honesty at chunk {chunkStr}
                </div>
                {ASOF_AXES.map((ax) => (
                  <div
                    key={ax.axis}
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      gap: 8,
                      fontSize: 12,
                    }}
                  >
                    <span
                      style={{
                        width: 14,
                        flex: "none",
                        textAlign: "center",
                        color: ax.color,
                      }}
                    >
                      {ax.glyph}
                    </span>
                    <span style={{ flex: 1 }}>{ax.axis}</span>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 9.5,
                        color: "hsl(var(--muted-foreground))",
                      }}
                    >
                      {ax.label}
                    </span>
                  </div>
                ))}
                <div
                  style={{
                    fontSize: 11,
                    color: "hsl(var(--muted-foreground))",
                    borderTop: "1px solid hsl(var(--border))",
                    paddingTop: 6,
                    fontStyle: "italic",
                  }}
                >
                  Never a binary honest/chimera switch — provenance is per-row.
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
        <HoverBtn
          title="Re-resolve tick"
          onClick={() => {
            void resolveQ.refetch();
          }}
          style={{
            width: 28,
            height: 28,
            border: "1px solid hsl(var(--border))",
            borderRadius: 6,
            background: "transparent",
            color: "hsl(var(--primary))",
            cursor: "pointer",
            fontSize: 15,
            flex: "none",
          }}
          hoverStyle={{
            borderColor: "hsl(var(--primary))",
            background: "hsl(var(--primary) / 0.12)",
          }}
        >
          ⟳
        </HoverBtn>
      </div>

      {/* override chips (pinned under tick bar) */}
      {overrides.length > 0 && (
        <div
          style={{
            flex: "none",
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 14px",
            borderBottom: "1px dashed hsl(var(--accent) / 0.5)",
            background: "hsl(var(--accent) / 0.07)",
          }}
        >
          <span
            className="font-mono"
            style={{
              fontSize: 9,
              letterSpacing: "0.2em",
              color: "hsl(var(--accent))",
              textTransform: "uppercase",
              flex: "none",
            }}
          >
            Sandbox overrides
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {overrides.map((oc, i) => (
              <span
                key={`${oc.label}:${i}`}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  border: "1px solid hsl(var(--accent) / 0.6)",
                  borderRadius: 99,
                  padding: "2px 4px 2px 10px",
                  fontSize: 11,
                  color: "hsl(var(--accent-foreground))",
                  background: "hsl(var(--accent) / 0.85)",
                }}
              >
                {oc.label}
                <button
                  type="button"
                  onClick={() => removeOverride(i)}
                  style={{
                    border: "none",
                    background: "hsl(var(--background) / 0.25)",
                    color: "inherit",
                    borderRadius: 99,
                    width: 16,
                    height: 16,
                    fontSize: 10,
                    cursor: "pointer",
                    lineHeight: 1,
                  }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ═══════════════ THREE REGIONS ═══════════════ */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <div style={{ height: "100%", display: "flex" }}>
          {/* ─────────── LEFT RAIL ─────────── */}
          <div style={{ width: "17%", minWidth: 200, height: "100%" }}>
            <div
              className="bg-sidebar"
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                borderRight: "1px solid hsl(var(--sidebar-border))",
                overflowY: "auto",
              }}
            >
              <div
                className="font-mono"
                style={{ ...railLabelStyle, padding: "12px 14px 6px" }}
              >
                Drive bands
              </div>
              {BAND_ORDER.map((b) => {
                const count = bandCounts?.[b] ?? 0;
                const col = bandColor(b);
                return (
                  <div
                    key={b}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      padding: "7px 14px",
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: 99,
                        background: col,
                        flex: "none",
                        boxShadow: `0 0 6px ${col.replace("))", ") / 0.5)")}`,
                      }}
                    />
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 10.5,
                        letterSpacing: "0.1em",
                        flex: 1,
                        color: "hsl(var(--sidebar-foreground))",
                      }}
                    >
                      {BAND_LABELS[b]}
                    </span>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 10,
                        minWidth: 20,
                        textAlign: "center",
                        border: `1px solid ${count ? col : "hsl(var(--border))"}`,
                        color: count ? col : "hsl(var(--muted-foreground))",
                        borderRadius: 99,
                        padding: "1px 6px",
                      }}
                    >
                      {count}
                    </span>
                  </div>
                );
              })}
              <div
                style={{
                  margin: "10px 14px",
                  borderTop: "1px solid hsl(var(--sidebar-border))",
                }}
              />
              <div
                className="font-mono"
                style={{ ...railLabelStyle, padding: "0 14px 8px" }}
              >
                Lenses
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 9,
                  padding: "0 14px 12px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, letterSpacing: "0.08em" }}
                  >
                    Two-party lane
                  </span>
                  <Switch checked={fTwoParty} onCheckedChange={setFTwoParty} />
                </div>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 4 }}
                >
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, letterSpacing: "0.08em" }}
                  >
                    Tag family
                  </span>
                  <Popover open={famOpen} onOpenChange={setFamOpen}>
                    <PopoverTrigger
                      className="font-mono"
                      style={{
                        width: "100%",
                        height: 28,
                        border: "1px solid hsl(var(--input))",
                        borderRadius: 6,
                        background: "transparent",
                        color: "hsl(var(--foreground))",
                        fontSize: 10,
                        letterSpacing: "0.06em",
                        cursor: "pointer",
                        textAlign: "left",
                        padding: "0 10px",
                      }}
                    >
                      {fFamily ?? "— none —"}
                    </PopoverTrigger>
                    <PopoverContent align="start">
                      <Command style={{ background: "transparent" }}>
                        <CommandInput placeholder="Filter families…" />
                        <CommandList>
                          <CommandEmpty>No family found.</CommandEmpty>
                          {familyEntries.map(([name, fam]) => (
                            <CommandItem
                              key={name}
                              value={name}
                              onSelect={() => {
                                setFFamily(fFamily === name ? null : name);
                                setFamOpen(false);
                              }}
                            >
                              <span
                                className="font-mono"
                                style={{
                                  fontSize: 10,
                                  letterSpacing: "0.06em",
                                }}
                              >
                                {name}
                              </span>
                              <span
                                style={{
                                  fontSize: 10,
                                  color: "hsl(var(--muted-foreground))",
                                  marginLeft: "auto",
                                }}
                              >
                                {fam.members.length}
                              </span>
                            </CommandItem>
                          ))}
                          <CommandItem
                            value="— clear —"
                            onSelect={() => {
                              setFFamily(null);
                              setFamOpen(false);
                            }}
                          >
                            <span
                              className="font-mono"
                              style={{ fontSize: 10, letterSpacing: "0.06em" }}
                            >
                              — clear —
                            </span>
                          </CommandItem>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 4 }}
                >
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, letterSpacing: "0.08em" }}
                  >
                    Event family
                  </span>
                  <Select value={fEvent} onValueChange={setFEvent}>
                    <SelectTrigger
                      style={{
                        height: 28,
                        width: "100%",
                        fontSize: 10.5,
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">— none —</SelectItem>
                      {eventOptions.map((ev) => (
                        <SelectItem key={ev} value={ev}>
                          {ev}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, letterSpacing: "0.08em" }}
                  >
                    Show gate-failed
                  </span>
                  <Switch checked={fFailed} onCheckedChange={setFFailed} />
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <span
                    className="font-mono"
                    style={{ fontSize: 10, letterSpacing: "0.08em" }}
                  >
                    Show not-applicable
                  </span>
                  <Switch checked={fNA} onCheckedChange={setFNA} />
                </div>
              </div>
              <div style={{ flex: 1 }} />
              <div
                className="font-mono"
                style={{
                  padding: "10px 14px",
                  fontSize: 9,
                  letterSpacing: "0.14em",
                  color: "hsl(var(--muted-foreground))",
                  borderTop: "1px solid hsl(var(--sidebar-border))",
                }}
              >
                {footerLine}
              </div>
            </div>
          </div>

          {/* ─────────── CENTER: STREAM / GRAPH ─────────── */}
          <div style={{ flex: 1, minWidth: 0, height: "100%" }}>
            <div
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                minWidth: 0,
              }}
            >
              <div
                style={{
                  flex: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "8px 14px 0",
                }}
              >
                <button
                  type="button"
                  className="font-mono"
                  style={tabStyle(centerTab === "stream")}
                  onClick={() => setCenterTab("stream")}
                >
                  Actor stream
                </button>
                <button
                  type="button"
                  className="font-mono"
                  style={tabStyle(centerTab === "graph")}
                  onClick={() => setCenterTab("graph")}
                >
                  Interaction graph
                </button>
                <div style={{ flex: 1 }} />
                <span
                  className="font-mono"
                  style={{
                    fontSize: 9.5,
                    letterSpacing: "0.1em",
                    color: "hsl(var(--muted-foreground))",
                  }}
                >
                  {streamSummary}
                </span>
              </div>

              {showEmptySlot && (
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <div
                    style={{
                      maxWidth: 380,
                      textAlign: "center",
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                      padding: 24,
                      border: "1px dashed hsl(var(--border))",
                      borderRadius: 8,
                    }}
                  >
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 10,
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: "hsl(var(--muted-foreground))",
                      }}
                    >
                      No Orrery data
                    </span>
                    <span
                      style={{
                        fontSize: 13,
                        color: "hsl(var(--muted-foreground))",
                        fontStyle: "italic",
                      }}
                    >
                      No off-screen actors resolve on this slot.
                    </span>
                  </div>
                </div>
              )}

              {!payload && (
                <div style={{ flex: 1, minHeight: 0 }} />
              )}

              {showStream && (
                <div
                  id="orr-stream"
                  style={{
                    flex: 1,
                    minHeight: 0,
                    overflowY: "auto",
                    padding: "10px 14px 24px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  {groups.map((g) => (
                    <StreamGroup
                      key={g.id}
                      g={g}
                      selectedActor={selection?.actor ?? null}
                      showFailedHint={!fFailed}
                      onHoverName={hoverNameHandler}
                      onHoverOut={hoverOut}
                    />
                  ))}
                  {/* on-screen scene row */}
                  <div
                    style={{
                      border: "1px dashed hsl(var(--border))",
                      borderRadius: 8,
                      padding: "9px 12px",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 9,
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: "hsl(var(--muted-foreground))",
                        flex: "none",
                      }}
                    >
                      On-screen
                    </span>
                    {onscreenChips.map((oc) => (
                      <span
                        key={oc.id}
                        onMouseEnter={hoverNameHandler(oc.id)}
                        onMouseLeave={hoverOut}
                        style={{
                          fontSize: 12.5,
                          fontWeight: 600,
                          color: "hsl(var(--foreground))",
                          textDecoration:
                            "underline dotted hsl(var(--primary) / 0.5)",
                          textUnderlineOffset: 3,
                          cursor: "default",
                        }}
                      >
                        {oc.name}
                      </span>
                    ))}
                    <span style={{ flex: 1 }} />
                    {needPressureChips.map((np) => (
                      <span
                        key={np.key}
                        className="font-mono"
                        title={np.title}
                        style={{
                          fontSize: 10,
                          letterSpacing: "0.05em",
                          border: "1px dashed hsl(var(--chart-2) / 0.7)",
                          color: "hsl(var(--chart-2))",
                          borderRadius: 99,
                          padding: "2px 9px",
                        }}
                      >
                        ⇢ {np.label}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {showGraph && payload && (
                <InteractionGraph
                  payload={payload}
                  selectedKey={selection?.key ?? null}
                  onSelect={(sel) => setSelection(sel)}
                  onHoverEntity={hoverIntent}
                  eventLens={eventLens}
                  deadArmConsumers={deadArmConsumers}
                />
              )}

              {/* ─────────── HEALTH STRIP ─────────── */}
              <HealthStrip {...health} />
            </div>
          </div>

          {/* ─────────── RIGHT: INSPECTOR ─────────── */}
          <div style={{ width: "30%", minWidth: 300, height: "100%" }}>
            <div
              style={{
                height: "100%",
                overflowY: "auto",
                borderLeft: "1px solid hsl(var(--border))",
                background: "hsl(var(--card) / 0.3)",
              }}
            >
              {inspector ? (
                <InspectorPane insp={inspector} />
              ) : (
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 30,
                  }}
                >
                  <div
                    style={{
                      textAlign: "center",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                      maxWidth: 240,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 22,
                        color: "hsl(var(--muted-foreground) / 0.5)",
                      }}
                    >
                      ◈
                    </span>
                    <span
                      className="font-mono"
                      style={{
                        fontSize: 9.5,
                        letterSpacing: "0.22em",
                        textTransform: "uppercase",
                        color: "hsl(var(--muted-foreground))",
                      }}
                    >
                      Inspector
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        fontStyle: "italic",
                        color: "hsl(var(--muted-foreground))",
                      }}
                    >
                      Select any card, ghost row, or pressure chip to open its
                      full gate trace and branch ladder.
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* what-if dashed sandbox frame */}
      {sandboxFrame && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            border: "2px dashed hsl(var(--accent) / 0.8)",
            zIndex: 50,
          }}
        >
          <span
            className="font-mono"
            style={{
              position: "absolute",
              bottom: 6,
              right: 12,
              fontSize: 9,
              letterSpacing: "0.24em",
              textTransform: "uppercase",
              color: "hsl(var(--accent))",
              background: "hsl(var(--background) / 0.85)",
              padding: "2px 8px",
            }}
          >
            Sandbox — not canon
          </span>
        </div>
      )}

      {/* floating hover-audit */}
      <HoverAudit
        ent={hoverVM}
        x={hoverPos.x}
        y={hoverPos.y}
        onEnter={hoverPanelEnter}
        onLeave={hoverOut}
      />

      {/* ═══════════════ WHAT-IF DRAWER ═══════════════ */}
      <WhatIfDrawer
        open={whatifOpen}
        onClose={() => setWhatifOpen(false)}
        entities={drawerEntities}
        vocab={vocabQ.data ?? null}
        needs={NEEDS}
        onApply={applyOverride}
        entityContext={entityContext}
      />
    </div>
  );
}
