/**
 * GateBrackets — vertical rail rendering of an evaluated gate tree.
 *
 * Port of the GateBrackets.dc.html prototype: each op node emits a small
 * uppercase mono label row and opens a colored rail (green-ish chart-5 when
 * the subtree passed, destructive when it failed) that runs down the left of
 * all its descendants; NOT rails additionally carry a rotated bar glyph.
 * Leaf rows show a ✓/✗ glyph, the predicate prose, and the right-aligned
 * mono evidence string.
 */
import type { CSSProperties } from "react";
import type { EvaluatedGateNode } from "./types";

interface Rail {
  color: string;
  barred: boolean;
  top: string;
  bottom: string;
}

interface OpRow {
  minH: number;
  rails: Rail[];
  isOp: true;
  isLeaf: false;
  op: string;
  opStyle: CSSProperties;
}

interface LeafRow {
  minH: number;
  rails: Rail[];
  isOp: false;
  isLeaf: true;
  glyph: string;
  glyphColor: string;
  prose: string;
  proseStyle: CSSProperties;
  evidence: string;
  evColor: string;
}

type Row = OpRow | LeafRow;

function railColor(n: EvaluatedGateNode): string {
  return n.pass ? "hsl(var(--chart-5) / 0.75)" : "hsl(var(--destructive) / 0.85)";
}

function buildRows(node: EvaluatedGateNode | null): Row[] {
  const rows: Row[] = [];
  if (!node) return rows;
  const walk = (n: EvaluatedGateNode | undefined, rails: Rail[]): void => {
    if (!n) return;
    if (n.kind === "leaf") {
      rows.push({
        minH: 20,
        rails: rails.map((r) => ({ ...r, top: "0", bottom: "0" })),
        isOp: false,
        isLeaf: true,
        glyph: n.pass ? "✓" : "✗",
        glyphColor: n.pass ? "hsl(var(--chart-5))" : "hsl(var(--destructive))",
        prose: n.prose,
        proseStyle: {
          flex: 1,
          fontSize: 11.5,
          minWidth: 0,
          ...(n.pass
            ? { color: "hsl(var(--foreground) / 0.85)" }
            : { color: "hsl(var(--foreground))", fontWeight: 650 }),
        },
        evidence: n.evidence,
        evColor: n.pass
          ? "hsl(var(--muted-foreground))"
          : "hsl(var(--destructive))",
      });
      return;
    }
    const color = railColor(n);
    const barred = n.op === "NOT";
    rows.push({
      minH: 18,
      rails: rails.map((r) => ({ ...r, top: "0", bottom: "0" })),
      isOp: true,
      isLeaf: false,
      op: (n.op ?? "") + (barred ? " ⊘" : ""),
      opStyle: {
        fontSize: 8.5,
        letterSpacing: "0.2em",
        padding: "3px 4px 1px",
        color,
        textTransform: "uppercase",
      },
    });
    const childRails: Rail[] = [
      ...rails,
      { color, barred, top: "0", bottom: "0" },
    ];
    for (const k of n.children ?? []) walk(k, childRails);
  };
  walk(node, []);
  // trim rail ends: first/last row of each depth — cosmetic; keep simple full bars
  return rows;
}

export default function GateBrackets({
  node,
}: {
  node: EvaluatedGateNode | null;
}) {
  const rows = buildRows(node);
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {rows.map((r, i) => (
        <div
          key={i}
          style={{ display: "flex", alignItems: "stretch", minHeight: r.minH }}
        >
          {r.rails.map((rl, j) => (
            <span
              key={j}
              style={{
                width: 16,
                flex: "none",
                position: "relative",
                display: "flex",
                justifyContent: "center",
              }}
            >
              <span
                style={{
                  width: 2,
                  background: rl.color,
                  position: "absolute",
                  top: rl.top,
                  bottom: rl.bottom,
                }}
              />
              {rl.barred && (
                <span
                  style={{
                    position: "absolute",
                    top: "45%",
                    width: 10,
                    height: 2,
                    background: rl.color,
                    transform: "rotate(-30deg)",
                  }}
                />
              )}
            </span>
          ))}
          {r.isOp && (
            <span className="font-mono" style={r.opStyle}>
              {r.op}
            </span>
          )}
          {r.isLeaf && (
            <span
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 7,
                padding: "2.5px 4px",
                flex: 1,
                minWidth: 0,
              }}
            >
              <span
                style={{
                  width: 13,
                  flex: "none",
                  textAlign: "center",
                  fontSize: 10,
                  color: r.glyphColor,
                }}
              >
                {r.glyph}
              </span>
              <span style={r.proseStyle}>{r.prose}</span>
              <span
                className="font-mono"
                style={{ fontSize: 9, color: r.evColor, flex: "none" }}
              >
                {r.evidence}
              </span>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
