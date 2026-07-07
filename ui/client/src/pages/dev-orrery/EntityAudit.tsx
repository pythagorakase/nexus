// Hover-audit card for a single entity: portrait/initials header, need
// meters, durable/ephemeral tag chips (family glyph + provenance dot,
// hover handlers feed the gate-highlight lens), relationships with the
// "unversioned" watermark, and recent events. Pure presentational —
// the VM is computed upstream by vm.buildEntityAudit.

import { useState } from "react";
import type { CSSProperties } from "react";
import type { EntityAuditTagVM, EntityAuditVM } from "./types";

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

const SECTION_LABEL: CSSProperties = {
  fontSize: 8,
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "hsl(var(--muted-foreground))",
};

function TagChip({
  tag,
  variant,
}: {
  tag: EntityAuditTagVM;
  variant: "durable" | "ephemeral";
}) {
  const [hover, setHover] = useState(false);
  const base: CSSProperties =
    variant === "durable"
      ? {
          border: "1px solid hsl(var(--border))",
          color: "hsl(var(--foreground) / 0.85)",
        }
      : {
          border: "1px dashed hsl(var(--chart-2) / 0.6)",
          color: "hsl(var(--chart-2))",
        };
  return (
    <span
      onMouseEnter={() => {
        setHover(true);
        tag.onEnter?.();
      }}
      onMouseLeave={() => {
        setHover(false);
        tag.onLeave?.();
      }}
      title={`${tag.famTitle} · ${tag.dotTitle}`}
      className="font-mono"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 9,
        letterSpacing: "0.04em",
        borderRadius: 99,
        padding: "1px 7px",
        cursor: "default",
        ...base,
        ...(hover ? { borderColor: "hsl(var(--accent))" } : {}),
      }}
    >
      <span style={{ color: "hsl(var(--chart-5))", fontSize: 8 }}>{tag.fam}</span>
      {tag.name}
      <span
        style={
          variant === "durable"
            ? { color: "hsl(var(--muted-foreground))", fontSize: 8 }
            : { opacity: 0.7, fontSize: 8 }
        }
      >
        {tag.dot}
      </span>
    </span>
  );
}

export default function EntityAudit({ ent }: { ent: EntityAuditVM }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 9,
        width: 290,
        fontFamily: "var(--font-sans)",
      }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        {/* Portrait placeholder: the app has no portrait pipeline on this
            page yet, so the prototype's image-slot is an initials circle. */}
        <div
          className="font-mono"
          style={{
            width: 46,
            height: 46,
            flex: "none",
            borderRadius: "50%",
            border: "1px solid hsl(var(--border))",
            background: "hsl(var(--muted) / 0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            letterSpacing: "0.06em",
            color: "hsl(var(--muted-foreground))",
          }}
        >
          {initialsOf(ent.name)}
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 1,
            minWidth: 0,
          }}
        >
          <span
            style={{
              fontSize: 14.5,
              fontWeight: 650,
              color: "hsl(var(--foreground))",
            }}
          >
            {ent.name}
          </span>
          <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>
            {ent.place}
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: 8.5,
              letterSpacing: "0.1em",
              color: "hsl(var(--muted-foreground) / 0.8)",
            }}
          >
            {ent.classes}
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: 8.5,
              letterSpacing: "0.06em",
              color: "hsl(var(--chart-5) / 0.9)",
            }}
          >
            {ent.fameRes}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {ent.needs.map((nr) => (
          <div
            key={nr.nd}
            style={{ display: "flex", alignItems: "center", gap: 7 }}
          >
            <span
              className="font-mono"
              style={{
                fontSize: 8.5,
                letterSpacing: "0.08em",
                width: 56,
                flex: "none",
                color: "hsl(var(--muted-foreground))",
              }}
            >
              {nr.nd}
            </span>
            <div
              style={{
                flex: 1,
                height: 3,
                borderRadius: 2,
                background: "hsl(var(--muted) / 0.3)",
                overflow: "hidden",
              }}
            >
              <div
                style={{ width: nr.pct, height: "100%", background: nr.color }}
              />
            </div>
            <span
              className="font-mono"
              style={{
                fontSize: 9,
                width: 52,
                textAlign: "right",
                color: nr.color,
              }}
            >
              {nr.val}
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: 7.5,
                width: 52,
                color: "hsl(var(--muted-foreground) / 0.7)",
              }}
            >
              {nr.note}
            </span>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="font-mono" style={SECTION_LABEL}>
          Durable
        </span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {ent.durable.map((tg, i) => (
            <TagChip key={`${tg.name}:${i}`} tag={tg} variant="durable" />
          ))}
        </div>
        {ent.hasEphemeral && (
          <>
            <span
              className="font-mono"
              style={{ ...SECTION_LABEL, marginTop: 2 }}
            >
              Ephemeral
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {ent.ephemeral.map((tg, i) => (
                <TagChip key={`${tg.name}:${i}`} tag={tg} variant="ephemeral" />
              ))}
            </div>
          </>
        )}
      </div>

      {ent.hasRels && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span className="font-mono" style={SECTION_LABEL}>
              Relationships
            </span>
            <span
              className="font-mono"
              style={{
                fontSize: 7.5,
                letterSpacing: "0.1em",
                color: "hsl(var(--muted-foreground) / 0.55)",
                fontStyle: "italic",
              }}
            >
              unversioned
            </span>
          </div>
          {ent.rels.map((rl, i) => (
            <div
              key={`${rl.other}:${i}`}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 7,
                fontSize: 11,
              }}
            >
              <span
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  color: "hsl(var(--chart-4))",
                  flex: "none",
                  minWidth: 70,
                }}
              >
                {rl.types}
              </span>
              <span style={{ flex: 1 }}>{rl.other}</span>
              <span
                className="font-mono"
                style={{ fontSize: 9.5, color: "hsl(var(--muted-foreground))" }}
              >
                trust {rl.trust}
              </span>
            </div>
          ))}
        </div>
      )}

      {ent.hasEvents && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 3,
            borderTop: "1px solid hsl(var(--border))",
            paddingTop: 6,
          }}
        >
          <span className="font-mono" style={SECTION_LABEL}>
            Recent events
          </span>
          {ent.events.map((ev, i) => (
            <div
              key={`${ev.t}:${ev.type}:${i}`}
              style={{ display: "flex", gap: 9, alignItems: "baseline" }}
            >
              <span
                className="font-mono"
                style={{ fontSize: 9, color: "hsl(var(--muted-foreground))" }}
              >
                {ev.t}
              </span>
              <span
                className="font-mono"
                style={{
                  fontSize: 9.5,
                  letterSpacing: "0.04em",
                  color: "hsl(var(--foreground) / 0.85)",
                }}
              >
                {ev.type}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
