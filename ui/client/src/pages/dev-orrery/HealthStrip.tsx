// Health strip — collapsible bottom drawer with four tile groups: winners by
// band, coverage gaps, never/always-win window stats, and dead gate arms +
// data quality. Port of the "Health strip" screen from the design prototype
// (Orrery Audit Dashboard.dc.html); all aggregation happens in the parent,
// this component just renders the view models it is handed.

import type { CSSProperties } from "react";

export interface HealthStripProps {
  open: boolean;
  onToggle: () => void;
  bands: { name: string; color: string; count: number; pct: string }[];
  gaps: { name: string; onJump: () => void }[];
  dominant: { id: string; share: string }[];
  neverWin: { id: string }[];
  deadArms: { event: string; consumers: string }[];
  dataQuality: { text: string; color: string }[];
  warnCount: string;
}

const tileStyle: CSSProperties = {
  border: "1px solid hsl(var(--border))",
  borderRadius: 6,
  padding: "10px 12px",
  display: "flex",
  flexDirection: "column",
};

const tileHeadingStyle: CSSProperties = {
  fontSize: 8.5,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "hsl(var(--muted-foreground))",
};

const barTrackStyle: CSSProperties = {
  flex: 1,
  height: 6,
  borderRadius: 3,
  background: "hsl(var(--muted) / 0.3)",
  overflow: "hidden",
};

export default function HealthStrip(props: HealthStripProps) {
  const {
    open,
    onToggle,
    bands,
    gaps,
    dominant,
    neverWin,
    deadArms,
    dataQuality,
    warnCount,
  } = props;

  return (
    <div
      className="bg-sidebar"
      style={{ flex: "none", borderTop: "1px solid hsl(var(--border))" }}
    >
      <div
        onClick={onToggle}
        className="hover:bg-muted/20"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "7px 14px",
          cursor: "pointer",
        }}
      >
        <span style={{ fontSize: 9, color: "hsl(var(--muted-foreground))" }}>
          {open ? "▾" : "▴"}
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
          System health
        </span>
        <span
          className="font-mono"
          style={{
            fontSize: 9.5,
            border: "1px solid hsl(var(--destructive) / 0.55)",
            color: "hsl(var(--destructive))",
            borderRadius: 99,
            padding: "0 7px",
          }}
        >
          {warnCount}
        </span>
        <div style={{ flex: 1 }} />
      </div>
      {open && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 10,
            padding: "0 14px 12px",
          }}
        >
          <div style={{ ...tileStyle, gap: 6 }}>
            <span className="font-mono" style={tileHeadingStyle}>
              Winners by band — this tick
            </span>
            {bands.map((hb) => (
              <div
                key={hb.name}
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: 9,
                    letterSpacing: "0.06em",
                    width: 86,
                    flex: "none",
                    color: "hsl(var(--muted-foreground))",
                  }}
                >
                  {hb.name}
                </span>
                <div style={barTrackStyle}>
                  <div
                    style={{ width: hb.pct, height: "100%", background: hb.color }}
                  />
                </div>
                <span
                  className="font-mono"
                  style={{ fontSize: 10, width: 14, textAlign: "right" }}
                >
                  {hb.count}
                </span>
              </div>
            ))}
          </div>
          <div style={{ ...tileStyle, gap: 6 }}>
            <span className="font-mono" style={tileHeadingStyle}>
              Coverage gaps — this tick
            </span>
            {gaps.length > 0 ? (
              gaps.map((hg) => (
                <button
                  key={hg.name}
                  onClick={hg.onJump}
                  className="hover:underline"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: "2px 0",
                    color: "hsl(var(--accent))",
                    fontSize: 12.5,
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: 99,
                      background: "hsl(var(--destructive))",
                    }}
                  />
                  {hg.name}
                  <span
                    className="font-mono"
                    style={{ fontSize: 9, color: "hsl(var(--muted-foreground))" }}
                  >
                    every gate refused
                  </span>
                </button>
              ))
            ) : (
              <span
                style={{
                  fontSize: 12,
                  fontStyle: "italic",
                  color: "hsl(var(--muted-foreground))",
                }}
              >
                Every candidate actor fired at least one package.
              </span>
            )}
          </div>
          <div style={{ ...tileStyle, gap: 5 }}>
            <span className="font-mono" style={tileHeadingStyle}>
              Never / always win — window
            </span>
            {dominant.map((hd) => (
              <div
                key={hd.id}
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: 9,
                    width: 96,
                    flex: "none",
                    letterSpacing: "0.04em",
                  }}
                >
                  {hd.id}
                </span>
                <div style={barTrackStyle}>
                  <div
                    style={{
                      width: hd.share,
                      height: "100%",
                      background: "hsl(var(--chart-1) / 0.8)",
                    }}
                  />
                </div>
                <span
                  className="font-mono"
                  style={{ fontSize: 9.5, width: 32, textAlign: "right" }}
                >
                  {hd.share}
                </span>
              </div>
            ))}
            <div
              style={{
                fontSize: 10.5,
                color: "hsl(var(--muted-foreground))",
                display: "flex",
                flexWrap: "wrap",
                gap: 4,
                marginTop: 2,
              }}
            >
              <span
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                }}
              >
                never:
              </span>
              {neverWin.map((hn) => (
                <span
                  key={hn.id}
                  className="font-mono"
                  style={{
                    fontSize: 9,
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 99,
                    padding: "0 6px",
                  }}
                >
                  {hn.id}
                </span>
              ))}
            </div>
          </div>
          <div
            style={{ ...tileStyle, gap: 5, overflowY: "auto", maxHeight: 170 }}
          >
            <span className="font-mono" style={tileHeadingStyle}>
              Dead gate arms · data quality
            </span>
            {deadArms.map((da) => (
              <div
                key={da.event}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 6,
                  fontSize: 10.5,
                }}
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: 9,
                    color: "hsl(var(--chart-5))",
                    flex: "none",
                  }}
                >
                  {da.event}
                </span>
                <span
                  style={{
                    color: "hsl(var(--muted-foreground))",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  → {da.consumers} · never emitted
                </span>
              </div>
            ))}
            <div
              style={{ borderTop: "1px solid hsl(var(--border))", margin: "3px 0" }}
            />
            {dataQuality.map((dq, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 7,
                  fontSize: 10.5,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 99,
                    background: dq.color,
                    flex: "none",
                    position: "relative",
                    top: -1,
                  }}
                />
                <span style={{ color: "hsl(var(--muted-foreground))" }}>
                  {dq.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
