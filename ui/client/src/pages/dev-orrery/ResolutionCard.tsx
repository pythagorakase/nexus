// ResolutionCard — winner card for a resolution stack, with an optional
// collapsible "shadowed" list of fired-but-outranked templates.
//
// Translated from ui/.design-sync/import/orrery/ResolutionCard.dc.html.
// The DCLogic block's wrapOpacity / cardStyle / isDial / isNumeric /
// shadowChev / shShadowBase computations are ported into the component body.
// Shadowed entries render inline via ShadowEntry (they are plain rows without
// their own shadow sections — no recursion into ResolutionCard).

import { useState } from "react";
import type { CSSProperties } from "react";

import type { ResolutionCardVM } from "./types";

export interface ResolutionCardProps {
  card: ResolutionCardVM;
  magnitudeStyle: "dial" | "numeric";
}

/** Shadowed sub-row: the sh.* template block from the prototype. */
function ShadowEntry({ sh }: { sh: ResolutionCardVM }) {
  const [hovered, setHovered] = useState(false);
  // shShadowBase from DCLogic, plus per-row band border + selection outline.
  // The prototype's `sh.outline` is not part of ResolutionCardVM; it is
  // derived here from `sh.selected` (the only selection signal the VM carries).
  const style: CSSProperties = {
    position: "relative",
    border: "1px solid hsl(var(--card-border) / 0.6)",
    borderRadius: 5,
    background: "hsl(var(--card) / 0.55)",
    padding: "6px 10px",
    cursor: "pointer",
    opacity: hovered ? 0.9 : 0.62,
    borderLeft: `3px solid ${sh.bandColor}`,
    outline: sh.selected ? "1px solid hsl(var(--primary) / 0.6)" : "none",
  };
  return (
    <div
      onClick={sh.onSelect}
      style={style}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="font-mono" style={{ fontSize: 10, letterSpacing: "0.1em" }}>
          {sh.tplName}
        </span>
        <span
          className="font-mono"
          style={{ fontSize: 8.5, color: "hsl(var(--muted-foreground))" }}
        >
          {sh.priority}
        </span>
        {sh.tie && (
          <span
            title={sh.tieTitle}
            className="font-mono"
            style={{
              fontSize: 8,
              border: "1px solid hsl(var(--chart-5) / 0.7)",
              color: "hsl(var(--chart-5))",
              borderRadius: 99,
              padding: "0 5px",
              cursor: "help",
            }}
          >
            tie
          </span>
        )}
        <span
          style={{
            fontSize: 10.5,
            color: "hsl(var(--muted-foreground))",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {sh.branchLabel}
        </span>
        <span
          className="font-mono"
          style={{ fontSize: 9.5, color: sh.bandColor, flex: "none" }}
        >
          {sh.mag?.text ?? ""}
        </span>
      </div>
    </div>
  );
}

export default function ResolutionCard({ card, magnitudeStyle }: ResolutionCardProps) {
  const [hovered, setHovered] = useState(false);

  // --- DCLogic port ---------------------------------------------------------
  const sel = card.selected;
  const wrapOpacity = card.dimByLens ? 0.35 : 1;
  const mag = card.mag;
  // The dial/numeric decision lives on the MagChip itself (vm.ts bakes
  // `magnitudeStyle` into `mag.dial` when building the chip); the prop is
  // accepted per the page's prop contract but the chip flag is authoritative.
  void magnitudeStyle;
  const isDial = !!(mag && mag.dial);
  const isNumeric = !!(mag && !mag.dial);
  const shadowChev = card.shadowOpen ? "▾" : "▸";

  const cardStyle: CSSProperties = {
    position: "relative",
    border: `1px solid ${sel ? "hsl(var(--primary))" : "hsl(var(--card-border))"}`,
    borderLeft: `3px solid ${card.bandColor}`,
    borderRadius: 6,
    background: "hsl(var(--card))",
    padding: `${card.pad || 10}px 12px`,
    cursor: "pointer",
    ...(card.highlight
      ? { boxShadow: "0 0 0 1px hsl(var(--chart-5) / 0.55)" }
      : sel
        ? { boxShadow: "0 0 0 1px hsl(var(--primary) / 0.6)" }
        : {}),
    // style-hover="border-color:hsl(var(--primary) / 0.55)" — the hover
    // declaration lands after the base border declarations, as in the DSL.
    ...(hovered ? { borderColor: "hsl(var(--primary) / 0.55)" } : {}),
  };
  // ---------------------------------------------------------------------------

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        opacity: wrapOpacity,
      }}
    >
      <div
        onClick={card.onSelect}
        style={cardStyle}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {card.diff && (
          <span
            title="Outcome changed vs pre-override tick"
            style={{
              position: "absolute",
              top: 8,
              right: 8,
              width: 7,
              height: 7,
              borderRadius: 99,
              background: "hsl(var(--accent))",
              boxShadow: "0 0 7px hsl(var(--accent))",
            }}
          />
        )}
        <div
          style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}
        >
          <span
            className="font-mono"
            style={{
              fontSize: 11,
              letterSpacing: "0.12em",
              color: "hsl(var(--foreground))",
            }}
          >
            {card.tplName}
          </span>
          {card.isPair && (
            <span style={{ fontSize: 11.5, color: "hsl(var(--muted-foreground))" }}>
              {"→ "}
              <span
                style={{ fontWeight: 600, color: "hsl(var(--foreground) / 0.9)" }}
              >
                {card.targetName}
              </span>
            </span>
          )}
          <span
            className="font-mono"
            style={{
              fontSize: 9,
              color: "hsl(var(--muted-foreground))",
              letterSpacing: "0.08em",
            }}
          >
            {card.priority}
          </span>
          {card.tie && (
            <span
              title={card.tieTitle}
              className="font-mono"
              style={{
                fontSize: 8.5,
                letterSpacing: "0.08em",
                border: "1px solid hsl(var(--chart-5) / 0.7)",
                color: "hsl(var(--chart-5))",
                borderRadius: 99,
                padding: "0 6px",
                cursor: "help",
              }}
            >
              tie
            </span>
          )}
          <span style={{ flex: 1 }} />
          {card.event && (
            <span
              className="font-mono"
              style={{
                fontSize: 9,
                letterSpacing: "0.06em",
                border: `1px solid ${card.bandColor}`,
                color: card.bandColor,
                borderRadius: 99,
                padding: "1px 8px",
                opacity: 0.9,
              }}
            >
              {card.event}
            </span>
          )}
          {isDial && mag && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                flex: "none",
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 99,
                  background: `conic-gradient(${mag.color} ${mag.deg ?? 0}deg, hsl(var(--muted) / 0.3) 0)`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <div
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 99,
                    background: "hsl(var(--card))",
                  }}
                />
              </div>
              <span
                className="font-mono"
                style={{ fontSize: 10.5, color: mag.color }}
              >
                {mag.text}
              </span>
            </div>
          )}
          {isNumeric && mag && (
            <span
              className="font-mono"
              style={{
                flex: "none",
                fontSize: 10.5,
                border: `1px solid ${mag.color}`,
                color: mag.color,
                borderRadius: 4,
                padding: "2px 7px",
              }}
            >
              {mag.text}
            </span>
          )}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "hsl(var(--muted-foreground))",
            marginTop: 4,
          }}
        >
          {card.branchLabel}
        </div>
      </div>
      {card.hasShadow && (
        <div
          style={{
            marginLeft: 12,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <button
            type="button"
            onClick={card.onToggleShadow}
            className="hover:opacity-80"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: "1px 0",
              width: "fit-content",
            }}
          >
            <span style={{ fontSize: 8, color: "hsl(var(--muted-foreground))" }}>
              {shadowChev}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: 8.5,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "hsl(var(--muted-foreground))",
              }}
            >
              shadowed
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: 9,
                border: "1px solid hsl(var(--border))",
                color: "hsl(var(--muted-foreground))",
                borderRadius: 99,
                padding: "0 6px",
              }}
            >
              {card.shadowCount}
            </span>
          </button>
          {card.shadowOpen && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {card.shadowed.map((sh) => (
                <ShadowEntry key={sh.key} sh={sh} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
