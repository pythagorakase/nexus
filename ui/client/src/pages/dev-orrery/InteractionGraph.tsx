// Interaction graph — SVG view of this tick's resolution: off-screen actors
// on a sine arc (left), on-screen entities in a right column, directed curved
// edges for two-party winners (band color), dashed accent edges for scene
// pressures, joint beats marked with the doubled-edge diamond, and dotted
// "potential event" arcs at the bottom when an event lens is active.
//
// Port of the "Interaction graph" screen from the design prototype (Orrery
// Audit Dashboard.dc.html, logic block ~lines 1068-1172). Differences from
// the prototype, driven by the live payload shape:
//   - onIds derivation: the payload has no explicit on-screen entity list, so
//     on-screen nodes are the union of scene_pressure_stacks target bindings
//     (present-target passes only bind on-screen entities by construction).
//   - on-screen node sublabel: the mock showed the entity's place name; the
//     live payload carries no place for non-actor entities, so it reads
//     "on-screen" instead.
//   - a no-solo-winner off-screen node click is a no-op here (the prototype
//     jumped to the actor's stream group — a parent-level concern that isn't
//     expressible through onSelect).
//   - SVG <text> renders normally in real JSX; the prototype's
//     React.createElement workaround for template holes inside <svg> is
//     unnecessary, and edge <title> tooltips live inside their edge group.

import * as React from "react";
import type {
  ResolvePayload,
  SelectionRef,
  StackPayload,
  TemplatePayload,
} from "./types";
import { actorHasFired, bandColor } from "./vm";

export interface InteractionGraphProps {
  payload: ResolvePayload;
  selectedKey: string | null;
  onSelect: (sel: SelectionRef) => void;
  onHoverEntity: (id: number, e: React.MouseEvent) => void;
  eventLens: string | null;
  deadArmConsumers: string[];
}

interface NodeVM {
  id: number;
  x: number;
  y: number;
  initials: string;
  name: string;
  stroke: string;
  strokeW: number;
  dash: string;
  sub: string;
  subColor: string;
  onClick: () => void;
}

interface PathBits {
  d: string;
  lx: number;
  ly: number;
  jx: number;
  jy: number;
}

interface EdgeVM extends PathBits {
  key: string;
  color: string;
  baseW: number;
  dash: string;
  baseOp: number;
  marker: string;
  label: string;
  title: string;
  joint: boolean;
  jrot: string;
  jly: number;
  sel: SelectionRef;
}

const initialsOf = (name: string): string =>
  name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

const winnerOf = (stack: StackPayload): TemplatePayload | null =>
  stack.templates.find((t) => t.is_winner) ?? null;

const markerFor = (band: string): string =>
  band === "crisis_constraint"
    ? "url(#arr1)"
    : band === "affiliation"
      ? "url(#arr4)"
      : "url(#arr5)";

const monoText = (
  fontSize: number,
  letterSpacing: string,
): React.CSSProperties => ({ fontSize, letterSpacing });

export default function InteractionGraph(props: InteractionGraphProps) {
  const {
    payload,
    selectedKey,
    onSelect,
    onHoverEntity,
    eventLens,
    deadArmConsumers,
  } = props;
  const [hoverEdge, setHoverEdge] = React.useState<string | null>(null);

  // Selection keys are "kind:actor:target:tpl" (see vm.ts buildCard).
  const selectedActor = selectedKey ? Number(selectedKey.split(":")[1]) : null;

  // ---------- layout ----------
  const offIds = payload.actors.map((g) => g.actor_entity_id);
  // On-screen entities: union of present-target (scene pressure) bindings.
  const onIds: number[] = [];
  const onNames = new Map<number, string>();
  for (const g of payload.actors) {
    for (const stack of g.scene_pressure_stacks) {
      const target = stack.bindings.target ?? null;
      if (target == null || offIds.includes(target) || onNames.has(target))
        continue;
      onIds.push(target);
      onNames.set(
        target,
        stack.binding_names.target ??
          payload.entity_names[String(target)] ??
          String(target),
      );
    }
  }

  // The prototype's sine arc was tuned for ~8 actors; real slots run 19+.
  // Fixed 72px vertical pitch keeps nodes legible and the svg grows (and
  // scrolls) with the roster instead of compressing it.
  const OFF_PITCH = 72;
  const svgHeight = Math.max(540, 90 + offIds.length * OFF_PITCH);
  const pos = new Map<number, { x: number; y: number }>();
  offIds.forEach((id, i) => {
    const t = i / Math.max(1, offIds.length - 1);
    pos.set(id, { x: 180 + Math.sin(t * Math.PI) * 130, y: 70 + i * OFF_PITCH });
  });
  onIds.forEach((id, i) => {
    pos.set(id, {
      x: 760,
      y: 120 + (i * (svgHeight - 200)) / Math.max(1, onIds.length - 1 || 1),
    });
  });

  const nameOf = (id: number): string =>
    payload.actors.find((g) => g.actor_entity_id === id)?.actor_name ??
    onNames.get(id) ??
    payload.entity_names[String(id)] ??
    String(id);

  // ---------- nodes ----------
  const nodes: NodeVM[] = [];
  for (const g of payload.actors) {
    const p = pos.get(g.actor_entity_id);
    if (!p) continue;
    const soloWinner = winnerOf(g.actor_stack);
    const gap = !actorHasFired(g);
    nodes.push({
      id: g.actor_entity_id,
      x: p.x,
      y: p.y,
      initials: initialsOf(g.actor_name),
      name: g.actor_name,
      stroke: gap
        ? "hsl(var(--destructive))"
        : soloWinner
          ? bandColor(soloWinner.drive_band)
          : "hsl(var(--border))",
      strokeW: selectedActor === g.actor_entity_id ? 2.8 : 1.6,
      dash: gap ? "3 3" : "1 0",
      sub: gap
        ? "coverage gap"
        : soloWinner
          ? soloWinner.template_id.toLowerCase()
          : "pairs only",
      subColor: gap
        ? "hsl(var(--destructive))"
        : soloWinner
          ? bandColor(soloWinner.drive_band)
          : "hsl(var(--muted-foreground))",
      onClick: soloWinner
        ? () =>
            onSelect({
              key: [
                "solo",
                g.actor_entity_id,
                "",
                soloWinner.template_id,
              ].join(":"),
              actor: g.actor_entity_id,
              target: null,
              tpl: soloWinner.template_id,
              kind: "solo",
            })
        : () => {},
    });
  }
  for (const id of onIds) {
    const p = pos.get(id);
    if (!p) continue;
    const name = onNames.get(id) ?? String(id);
    nodes.push({
      id,
      x: p.x,
      y: p.y,
      initials: initialsOf(name),
      name,
      stroke: "hsl(var(--primary) / 0.7)",
      strokeW: selectedActor === id ? 2.8 : 1.6,
      dash: "1 0",
      sub: "on-screen",
      subColor: "hsl(var(--muted-foreground))",
      onClick: () => {},
    });
  }

  // ---------- edges ----------
  const isRecip = (a: number, b: number): boolean =>
    payload.joint_beats.some(
      (jb) =>
        (jb.entity_a === a && jb.entity_b === b) ||
        (jb.entity_a === b && jb.entity_b === a),
    );
  const mkPath = (a: number, b: number, bend: number, shrink = 22): PathBits => {
    const pa = pos.get(a)!;
    const pb = pos.get(b)!;
    const dx = pb.x - pa.x;
    const dy = pb.y - pa.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const sx = pa.x + ux * shrink;
    const sy = pa.y + uy * shrink;
    const ex = pb.x - ux * shrink;
    const ey = pb.y - uy * shrink;
    const mx = (sx + ex) / 2 - uy * bend;
    const my = (sy + ey) / 2 + ux * bend;
    return {
      d: `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`,
      lx: mx,
      ly: my - 6,
      jx: mx - 4.5,
      jy: my - 4.5,
    };
  };

  const edges: EdgeVM[] = [];
  for (const g of payload.actors) {
    for (const stack of g.two_party_stacks) {
      const winner = winnerOf(stack);
      const target = stack.bindings.target ?? null;
      if (!winner || target == null || !pos.has(target)) continue;
      const joint = isRecip(g.actor_entity_id, target);
      const key = ["pair", g.actor_entity_id, target, winner.template_id].join(
        ":",
      );
      const path = mkPath(g.actor_entity_id, target, joint ? 16 : 12);
      edges.push({
        ...path,
        key,
        color: bandColor(winner.drive_band),
        baseW: 1.6,
        dash: "1 0",
        baseOp: 0.95,
        marker: markerFor(winner.drive_band),
        label: winner.template_id.toLowerCase(),
        title: `${winner.template_id} · ${g.actor_name} → ${nameOf(target)} · “${winner.chosen_branch ?? ""}” · mag ${(winner.magnitude ?? 0).toFixed(2)}`,
        joint: joint && g.actor_entity_id < target,
        jrot: `rotate(45 ${path.jx + 4.5} ${path.jy + 4.5})`,
        jly: path.ly + 26,
        sel: {
          key,
          actor: g.actor_entity_id,
          target,
          tpl: winner.template_id,
          kind: "pair",
        },
      });
    }
    for (const stack of g.scene_pressure_stacks) {
      const winner = winnerOf(stack);
      const target = stack.bindings.target ?? null;
      if (!winner || target == null || !pos.has(target)) continue;
      const key = [
        "pressure",
        g.actor_entity_id,
        target,
        winner.template_id,
      ].join(":");
      const path = mkPath(g.actor_entity_id, target, 24);
      edges.push({
        ...path,
        key,
        color: "hsl(var(--accent))",
        baseW: 1.3,
        dash: "5 4",
        baseOp: 0.8,
        marker: "url(#arrA)",
        label: winner.template_id.toLowerCase() + " ⇢",
        title: `${winner.template_id} pressure · ${g.actor_name} ⇢ ${nameOf(target)} · prompt-only, no state mutation · mag ${(winner.magnitude ?? 0).toFixed(2)}`,
        joint: false,
        jrot: "",
        jly: 0,
        sel: {
          key,
          actor: g.actor_entity_id,
          target,
          tpl: winner.template_id,
          kind: "pressure",
        },
      });
    }
  }
  const selEdgeActive = edges.some((e) => e.key === selectedKey);
  const edgeW = (e: EdgeVM): number =>
    e.key === selectedKey ? 3 : hoverEdge === e.key ? 2.5 : e.baseW;
  const edgeOp = (e: EdgeVM): number =>
    e.key === selectedKey
      ? 1
      : selEdgeActive
        ? 0.3
        : hoverEdge && hoverEdge !== e.key
          ? 0.5
          : e.baseOp;

  // ---------- potential-event arcs ----------
  const potentialActive = eventLens != null;
  const potentialConsumers = potentialActive
    ? deadArmConsumers.map((c, i) => ({
        name: c,
        x: 250 + i * 160,
        y: 508,
        d: `M 74 456 Q ${150 + i * 140} 495 ${245 + i * 160} 503`,
      }))
    : [];

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "6px 14px 20px" }}>
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "center",
          flexWrap: "wrap",
          padding: "2px 4px 10px",
          maxWidth: 1400,
          margin: "0 auto",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10.5,
            color: "hsl(var(--muted-foreground))",
          }}
        >
          <span
            style={{
              width: 18,
              height: 0,
              borderTop: "2px solid hsl(var(--chart-4))",
              display: "inline-block",
            }}
          />
          fired package · band color
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10.5,
            color: "hsl(var(--muted-foreground))",
          }}
        >
          <span
            style={{
              width: 18,
              height: 0,
              borderTop: "2px dashed hsl(var(--accent))",
              display: "inline-block",
            }}
          />
          scene pressure → on-screen
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10.5,
            color: "hsl(var(--muted-foreground))",
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              border: "1.4px solid hsl(var(--chart-4))",
              transform: "rotate(45deg)",
              display: "inline-block",
            }}
          />
          reciprocal joint beat
        </span>
        <span
          className="font-mono"
          style={{
            marginLeft: "auto",
            fontSize: 9,
            letterSpacing: "0.1em",
            color: "hsl(var(--muted-foreground))",
          }}
        >
          hover a node for its audit · click an edge to trace it
        </span>
      </div>
      <svg
        viewBox={`0 0 920 ${svgHeight}`}
        style={{
          width: "100%",
          maxWidth: 1400,
          height: "auto",
          display: "block",
          margin: "0 auto",
        }}
      >
        <defs>
          <marker
            id="arr1"
            viewBox="0 0 8 8"
            refX={7}
            refY={4}
            markerWidth={7}
            markerHeight={7}
            orient="auto-start-reverse"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="hsl(var(--chart-1))" />
          </marker>
          <marker
            id="arr4"
            viewBox="0 0 8 8"
            refX={7}
            refY={4}
            markerWidth={7}
            markerHeight={7}
            orient="auto-start-reverse"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="hsl(var(--chart-4))" />
          </marker>
          <marker
            id="arr5"
            viewBox="0 0 8 8"
            refX={7}
            refY={4}
            markerWidth={7}
            markerHeight={7}
            orient="auto-start-reverse"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="hsl(var(--chart-5))" />
          </marker>
          <marker
            id="arrA"
            viewBox="0 0 8 8"
            refX={7}
            refY={4}
            markerWidth={7}
            markerHeight={7}
            orient="auto-start-reverse"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="hsl(var(--accent))" />
          </marker>
        </defs>
        <text
          x={70}
          y={30}
          className="font-mono"
          style={{ fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase" }}
          fill="hsl(var(--muted-foreground))"
        >
          Off-screen actors
        </text>
        <text
          x={700}
          y={30}
          className="font-mono"
          style={{ fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase" }}
          fill="hsl(var(--muted-foreground))"
        >
          On-screen
        </text>
        <line
          x1={640}
          y1={40}
          x2={640}
          y2={440}
          stroke="hsl(var(--border))"
          strokeDasharray="2 5"
        />
        {edges.map((e) => {
          const w = edgeW(e);
          const op = edgeOp(e);
          return (
            <g
              key={e.key}
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(e.sel)}
              onMouseEnter={() => setHoverEdge(e.key)}
              onMouseLeave={() => setHoverEdge(null)}
            >
              <title>{e.title}</title>
              <path
                d={e.d}
                fill="none"
                stroke="transparent"
                strokeWidth={16}
                pointerEvents="stroke"
              />
              <path
                d={e.d}
                fill="none"
                stroke={e.color}
                strokeWidth={w}
                strokeDasharray={e.dash}
                markerEnd={e.marker}
                opacity={op}
                pointerEvents="none"
              />
              {e.joint && (
                <g pointerEvents="none">
                  <rect
                    x={e.jx}
                    y={e.jy}
                    width={9}
                    height={9}
                    transform={e.jrot}
                    fill="hsl(var(--background))"
                    stroke={e.color}
                    strokeWidth={1.4}
                  />
                  <text
                    x={e.lx}
                    y={e.jly}
                    className="font-mono"
                    style={monoText(8, "0.1em")}
                    fill="hsl(var(--muted-foreground))"
                    textAnchor="middle"
                  >
                    joint beat
                  </text>
                </g>
              )}
              <text
                x={e.lx}
                y={e.ly}
                textAnchor="middle"
                className="font-mono"
                style={monoText(8.5, "0.08em")}
                fill={e.color}
                opacity={op}
                pointerEvents="none"
              >
                {e.label}
              </text>
            </g>
          );
        })}
        {nodes.map((n) => (
          <g
            key={n.id}
            style={{ cursor: "pointer" }}
            onClick={n.onClick}
            onMouseEnter={(e) => onHoverEntity(n.id, e)}
          >
            <circle
              cx={n.x}
              cy={n.y}
              r={19}
              fill="hsl(var(--card))"
              stroke={n.stroke}
              strokeWidth={n.strokeW}
              strokeDasharray={n.dash}
            />
            <text
              x={n.x}
              y={n.y + 3.5}
              textAnchor="middle"
              className="font-mono"
              style={{ fontSize: 10.5 }}
              fill="hsl(var(--foreground))"
              pointerEvents="none"
            >
              {n.initials}
            </text>
            <text
              x={n.x}
              y={n.y + 34}
              textAnchor="middle"
              style={{ fontSize: 11, fontWeight: 600 }}
              fill="hsl(var(--foreground) / 0.9)"
              pointerEvents="none"
            >
              {n.name}
            </text>
            <text
              x={n.x}
              y={n.y + 46}
              textAnchor="middle"
              className="font-mono"
              style={{
                fontSize: 7.5,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
              fill={n.subColor}
              pointerEvents="none"
            >
              {n.sub}
            </text>
          </g>
        ))}
        {potentialActive && (
          <g>
            <rect
              x={60}
              y={452}
              width={9}
              height={9}
              transform="rotate(45 64.5 456.5)"
              fill="none"
              stroke="hsl(var(--muted-foreground))"
              strokeWidth={1.2}
            />
            <text
              x={80}
              y={461}
              className="font-mono"
              style={monoText(9.5, "0.1em")}
              fill="hsl(var(--foreground))"
            >
              {eventLens}
            </text>
            <text
              x={80}
              y={476}
              className="font-mono"
              style={monoText(8, "0.08em")}
              fill="hsl(var(--muted-foreground))"
            >
              consumed by gates · emitted by no branch — potential, never realized
            </text>
            {potentialConsumers.map((pc) => (
              <g key={pc.name}>
                <path
                  d={pc.d}
                  fill="none"
                  stroke="hsl(var(--muted-foreground))"
                  strokeWidth={1}
                  strokeDasharray="1.5 4"
                  opacity={0.65}
                />
                <text
                  x={pc.x}
                  y={pc.y}
                  className="font-mono"
                  style={monoText(8.5, "0.08em")}
                  fill="hsl(var(--muted-foreground))"
                >
                  {pc.name}
                </text>
              </g>
            ))}
          </g>
        )}
      </svg>
    </div>
  );
}
