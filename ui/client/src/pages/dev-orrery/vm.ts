// Adapter: live /api/dev/orrery payloads -> the view models the design
// prototype's components render. This is the port of the prototype's
// DCLogic (Orrery Audit Dashboard.dc.html) with the mock engine's shapes
// replaced by the real API contract:
//   - what-if diffs come from the server (`stack.diff`), not a second resolve
//   - joint beats come from `payload.joint_beats`, not reciprocalPairs()
//   - evidence is the structured dict from the evidence layer, formatted
//     into the compact mono string the inspector right-column shows
//   - band ids are the live drive_band values, not the mock's short ids

import type {
  ActorGroupPayload,
  ActorGroupVM,
  ContextEntity,
  EntityAuditVM,
  EvaluatedGateNode,
  GhostRowVM,
  InspectorVM,
  MagChip,
  PressureChipVM,
  ResolutionCardVM,
  ResolvePayload,
  RowStatus,
  SelectionRef,
  StackPayload,
  TemplatePayload,
  TraceEvidence,
  TraceNode,
} from "./types";

// ---------------------------------------------------------------------------
// Bands: live drive_band value -> chart token (five bands, five tokens)
// ---------------------------------------------------------------------------

export const BAND_CHART: Record<string, number> = {
  crisis_constraint: 1,
  embodied_maintenance: 2,
  anchored_routine: 3,
  affiliation: 4,
  project_identity: 5,
};

export const BAND_LABELS: Record<string, string> = {
  crisis_constraint: "Crisis / Constraint",
  embodied_maintenance: "Embodied Maintenance",
  anchored_routine: "Anchored Routine",
  affiliation: "Affiliation",
  project_identity: "Project / Identity",
};

export const BAND_ORDER = [
  "crisis_constraint",
  "embodied_maintenance",
  "anchored_routine",
  "affiliation",
  "project_identity",
];

export const NEEDS = ["sleep", "thirst", "hunger", "socialize", "intimacy"];

export function bandColor(band: string): string {
  return `hsl(var(--chart-${BAND_CHART[band] ?? 5}))`;
}

// ---------------------------------------------------------------------------
// Evidence: structured dict -> compact mono string
// ---------------------------------------------------------------------------

const fmtNum = (v: unknown): string =>
  typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(1)) : String(v);

/** Render the evidence layer's structured payload as the short observed-value
 * string the inspector's right column and the gate brackets show. */
export function evidenceText(ev: TraceEvidence | null | undefined): string {
  if (!ev) return "";
  const o = ev.observed ?? {};
  const matched = (ev.matched ?? []) as unknown[];
  switch (ev.kind) {
    case "always":
      return "always";
    case "never":
      return "never";
    case "has_need_debt_at_or_above":
      return `${fmtNum(o.debt_score)} ${ev.result ? "≥" : "<"} ${fmtNum(
        (ev.params as Record<string, unknown>).threshold,
      )}`;
    case "trust_at_least":
    case "trust_below":
      return `trust ${fmtNum(o.trust)}`;
    case "relationship_is_mutual_warm":
    case "relationship_is_asymmetric":
      return `${fmtNum(o.forward_trust)} / ${fmtNum(o.reverse_trust)}`;
    case "direct_contact_is_dramatic":
      return matched.length ? String(matched.join(", ")) : "no trigger";
    case "time_of_day_in":
      return String(o.time_of_day ?? "");
    case "weather_is":
      return String(o.weather ?? "");
    case "since_last_event_at_least": {
      const elapsed = o.elapsed_ticks;
      return elapsed == null ? "never fired" : `${fmtNum(elapsed)} ticks ago`;
    }
    case "recent_event":
      return matched.length
        ? `${matched.length} in window`
        : "none in window";
    case "in_location_class":
    case "in_location":
      return o.place_id == null ? "no place" : `place ${fmtNum(o.place_id)}`;
    case "has_location_class_destination":
      return `${fmtNum(o.destination_count)} candidates`;
    case "count_co_located":
      return `${fmtNum(o.count)} present`;
    case "co_located": {
      const places = (o.places ?? {}) as Record<string, unknown>;
      return Object.values(places).map(fmtNum).join(" · ");
    }
    case "fame_at_or_above":
    case "fame_below":
    case "resources_at_or_above":
    case "resources_below":
      return `${String(o.resolved_tier)}${o.defaulted ? " (default)" : ""}`;
    case "has_any_status_at_or_above":
      return matched.length
        ? String((matched[0] as Record<string, unknown>).tag)
        : "no standing";
    case "travel_progress_at_or_above":
      return o.progress_ratio == null ? "not traveling" : fmtNum(o.progress_ratio);
    case "is_in_transit":
      return String(o.travel_status ?? "no travel state");
    default: {
      // Family/tag/pair predicates and anything else: matched members are
      // the story; otherwise summarize the first observed value.
      if (matched.length) {
        return matched
          .slice(0, 3)
          .map((m) =>
            typeof m === "object" && m !== null
              ? String(Object.values(m as Record<string, unknown>)[0])
              : String(m),
          )
          .join(", ");
      }
      const first = Object.entries(o)[0];
      if (!first) return ev.result === false ? "no match" : "";
      const [, v] = first;
      if (Array.isArray(v)) {
        if (!v.length) return "none";
        const shown = v.slice(0, 3).map(fmtNum).join(", ");
        return v.length > 3 ? `${shown} +${v.length - 3}` : shown;
      }
      return v == null ? "—" : fmtNum(v);
    }
  }
}

/** Tags a leaf's evidence references (for tag-hover highlighting). */
export function evidenceReads(ev: TraceEvidence | null | undefined): string[] {
  if (!ev) return [];
  const reads = new Set<string>();
  const p = ev.params as Record<string, unknown>;
  for (const key of ["tag", "tags", "family_members"]) {
    const v = p[key];
    if (typeof v === "string") reads.add(v);
    if (Array.isArray(v)) for (const t of v) reads.add(String(t));
  }
  for (const m of ev.matched ?? []) if (typeof m === "string") reads.add(m);
  return Array.from(reads);
}

// ---------------------------------------------------------------------------
// Gate trees
// ---------------------------------------------------------------------------

/** Live TraceNode -> the EvaluatedGateNode shape GateBrackets renders. */
export function toGateNode(node: TraceNode): EvaluatedGateNode {
  if (node.op) {
    return {
      kind: "op",
      op: node.op,
      pass: node.result,
      prose: node.op,
      evidence: "",
      reads: [],
      children: (node.children ?? []).map(toGateNode),
    };
  }
  return {
    kind: "leaf",
    pass: node.result,
    prose: node.prose,
    evidence: evidenceText(node.evidence),
    reads: evidenceReads(node.evidence),
  };
}

export interface FailLeaf {
  prose: string;
  evidence: string;
  negated: boolean;
}

/** First failing leaf on the gate's failure path (ghost-row reason line).
 * Under NOT, a *passing* leaf is the blocker. */
export function firstFailingLeaf(node: TraceNode, negated = false): FailLeaf | null {
  if (!node.op) {
    const failsHere = negated ? node.result : !node.result;
    return failsHere
      ? { prose: node.prose, evidence: evidenceText(node.evidence), negated }
      : null;
  }
  const kids = node.children ?? [];
  if (node.op === "NOT") return kids[0] ? firstFailingLeaf(kids[0], !negated) : null;
  const gateFails = negated ? node.result : !node.result;
  if (!gateFails) return null;
  for (const child of kids) {
    const hit = firstFailingLeaf(child, negated);
    if (hit) return hit;
  }
  return null;
}

/** Whether any leaf of the gate reads a member of `members` (family lens). */
export function gateReadsAny(node: TraceNode, members: string[]): boolean {
  if (!node.op) return evidenceReads(node.evidence).some((t) => members.includes(t));
  return (node.children ?? []).some((c) => gateReadsAny(c, members));
}

/** Whether the gate consumes the given event type (event lens). */
export function gateConsumesEvent(node: TraceNode, eventType: string): boolean {
  if (!node.op)
    return (
      (node.raw.startsWith("recent_event(") ||
        node.raw.startsWith("since_last_event_at_least(")) &&
      node.raw.includes(eventType)
    );
  return (node.children ?? []).some((c) => gateConsumesEvent(c, eventType));
}

// ---------------------------------------------------------------------------
// Rows and cards
// ---------------------------------------------------------------------------

export function rowStatus(t: TemplatePayload): RowStatus {
  if (t.is_winner) return "winner";
  if (t.is_shadowed) return "shadowed";
  return "gate_failed";
}

export function magChip(
  mag: number,
  color: string,
  style: "dial" | "numeric",
): MagChip {
  return style === "dial"
    ? { dial: true, deg: Math.round(mag * 360), color, text: mag.toFixed(2) }
    : { dial: false, color, text: mag.toFixed(2) };
}

export interface CardBuildCtx {
  selectedKey: string | null;
  familyMembers: string[] | null;
  eventLens: string | null;
  magnitudeStyle: "dial" | "numeric";
  pad: number;
  ties: Map<string, string[]>;
  shadowOpen: Record<string, boolean>;
  select: (sel: SelectionRef) => void;
  toggleShadow: (key: string) => void;
}

function buildCard(
  group: ActorGroupPayload,
  stack: StackPayload,
  t: TemplatePayload,
  kind: "solo" | "pair",
  ctx: CardBuildCtx,
): ResolutionCardVM {
  const target = kind === "pair" ? (stack.bindings.target ?? null) : null;
  const key = [kind, group.actor_entity_id, target ?? "", t.template_id].join(":");
  const col = bandColor(t.drive_band);
  const famHit = ctx.familyMembers
    ? gateReadsAny(t.gate_trace, ctx.familyMembers)
    : false;
  const evHit = ctx.eventLens ? gateConsumesEvent(t.gate_trace, ctx.eventLens) : false;
  const tie = ctx.ties.get(t.template_id) ?? null;
  const diff =
    !!stack.diff &&
    (stack.diff.changed_template_ids.includes(t.template_id) ||
      (t.is_winner && stack.diff.changed));
  return {
    key,
    kind,
    tplName: t.template_id,
    priority: `pri ${t.priority}`,
    bandColor: col,
    dim: t.is_shadowed,
    tie: !!tie,
    tieTitle: tie
      ? `priority tied with ${tie.join(", ")} — authored tuple order decided`
      : "",
    isPair: kind === "pair",
    targetName: target != null ? (stack.binding_names.target ?? String(target)) : null,
    targetEntityId: target,
    branchLabel: t.chosen_branch ?? "",
    event: t.event_type,
    mag:
      t.magnitude != null ? magChip(t.magnitude, col, ctx.magnitudeStyle) : null,
    selected: ctx.selectedKey === key,
    diff,
    highlight: famHit || evHit,
    dimByLens:
      (!!ctx.familyMembers && !famHit) || (!!ctx.eventLens && !evHit),
    pad: ctx.pad,
    shadowCount: 0,
    hasShadow: false,
    shadowOpen: false,
    shadowed: [],
    onSelect: () =>
      ctx.select({
        key,
        actor: group.actor_entity_id,
        target,
        tpl: t.template_id,
        kind,
      }),
  };
}

function attachShadow(
  card: ResolutionCardVM,
  group: ActorGroupPayload,
  stack: StackPayload,
  kind: "solo" | "pair",
  shadowKey: string,
  ctx: CardBuildCtx,
): void {
  const shadowed = stack.templates.filter((t) => t.is_shadowed);
  card.shadowCount = shadowed.length;
  card.hasShadow = shadowed.length > 0;
  card.shadowOpen = !!ctx.shadowOpen[shadowKey];
  card.shadowed = shadowed.map((t) => buildCard(group, stack, t, kind, ctx));
  card.onToggleShadow = () => ctx.toggleShadow(shadowKey);
}

// ---------------------------------------------------------------------------
// Groups
// ---------------------------------------------------------------------------

/**
 * Whether anything fired for this actor across all three stack kinds. A
 * pressure fire counts as coverage (prototype: `fires.length === 0 &&
 * pressures.length === 0`) — actors whose only activity is scene pressure
 * are not coverage gaps. Shared by the stream (gap notice, avatar ring)
 * and InteractionGraph (dotted gap nodes) so the two can never disagree.
 */
export function actorHasFired(g: ActorGroupPayload): boolean {
  return [g.actor_stack, ...g.two_party_stacks, ...g.scene_pressure_stacks].some(
    (s) => s.templates.some((t) => t.fired),
  );
}

export interface GroupBuildCtx extends CardBuildCtx {
  showTwoPartyOnly: boolean;
  showFailed: boolean;
  showNA: boolean;
  groupOpen: Record<number, boolean>;
  toggleGroup: (id: number) => void;
}

export function buildGroups(
  payload: ResolvePayload,
  ctx: GroupBuildCtx,
): ActorGroupVM[] {
  return payload.actors.map((g) => {
    const open = ctx.groupOpen[g.actor_entity_id] !== false;
    const soloWinner = g.actor_stack.templates.find((t) => t.is_winner) ?? null;
    const cards: ResolutionCardVM[] = [];

    if (soloWinner && !ctx.showTwoPartyOnly) {
      const c = buildCard(g, g.actor_stack, soloWinner, "solo", ctx);
      attachShadow(c, g, g.actor_stack, "solo", `solo:${g.actor_entity_id}`, ctx);
      cards.push(c);
    }
    for (const stack of g.two_party_stacks) {
      const winner = stack.templates.find((t) => t.is_winner);
      if (!winner) continue;
      const c = buildCard(g, stack, winner, "pair", ctx);
      attachShadow(
        c,
        g,
        stack,
        "pair",
        `pair:${g.actor_entity_id}:${stack.bindings.target}`,
        ctx,
      );
      cards.push(c);
    }

    const pressures: PressureChipVM[] = g.scene_pressure_stacks.flatMap((stack) => {
      const winner = stack.templates.find((t) => t.is_winner);
      if (!winner) return [];
      const target = stack.bindings.target;
      const key = ["pressure", g.actor_entity_id, target, winner.template_id].join(":");
      return [
        {
          key,
          label: `${winner.template_id} → ${
            stack.binding_names.target ?? target
          } · ${(winner.magnitude ?? 0).toFixed(2)}`,
          title: winner.scene_pressure_prompt_rendered ?? "",
          selected: ctx.selectedKey === key,
          diff: !!stack.diff?.changed,
          onSelect: () =>
            ctx.select({
              key,
              actor: g.actor_entity_id,
              target,
              tpl: winner.template_id,
              kind: "pressure",
            }),
        },
      ];
    });

    const ghosts: GhostRowVM[] = [];
    if (ctx.showFailed) {
      const pushFailures = (
        stack: StackPayload,
        kind: "solo" | "pair",
        target: number | null,
        suffix: string,
      ) => {
        for (const t of stack.templates) {
          if (t.fired || t.gate_passed) continue;
          const key = [kind, g.actor_entity_id, target ?? "", t.template_id].join(":");
          const fail = firstFailingLeaf(t.gate_trace);
          ghosts.push({
            key,
            name: t.template_id + suffix,
            glyph: "✗",
            status: "gate_failed",
            reason: fail
              ? `${fail.negated ? "blocked: " : "failed: "}${fail.prose}`
              : "gate refused",
            evidence: fail?.evidence ?? "",
            na: false,
            selected: ctx.selectedKey === key,
            onSelect: () =>
              ctx.select({
                key,
                actor: g.actor_entity_id,
                target,
                tpl: t.template_id,
                kind,
              }),
          });
        }
      };
      if (!ctx.showTwoPartyOnly) pushFailures(g.actor_stack, "solo", null, "");
      for (const stack of g.two_party_stacks) {
        const target = stack.bindings.target;
        pushFailures(
          stack,
          "pair",
          target,
          ` → ${stack.binding_names.target ?? target}`,
        );
      }
    }
    if (ctx.showNA) {
      for (const marker of g.not_applicable) {
        const key = ["na", g.actor_entity_id, "", marker.template_id].join(":");
        ghosts.push({
          key,
          name: marker.template_id,
          glyph: "⊘",
          status: "not_applicable",
          reason: "not applicable — no TARGET bound in this stack",
          evidence: "slots: ACTOR, TARGET",
          na: true,
          selected: ctx.selectedKey === key,
          onSelect: () =>
            ctx.select({
              key,
              actor: g.actor_entity_id,
              target: null,
              tpl: marker.template_id,
              kind: "na",
            }),
        });
      }
    }

    const gap = !actorHasFired(g);
    const visibleCards = ctx.showTwoPartyOnly ? cards.filter((c) => c.isPair) : cards;
    const diff =
      cards.some((c) => c.diff) || pressures.some((p) => p.diff);

    return {
      id: g.actor_entity_id,
      domId: `group-${g.actor_entity_id}`,
      name: g.actor_name,
      initials: g.actor_name
        .split(/\s+/)
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase(),
      ringColor: gap
        ? "hsl(var(--destructive) / 0.7)"
        : soloWinner
          ? bandColor(soloWinner.drive_band)
          : "hsl(var(--border))",
      placeName: g.location?.name ?? "—",
      open,
      gap,
      diff,
      cards: visibleCards,
      pressures,
      ghosts,
      bandDots: visibleCards
        .filter((c) => !c.dim)
        .map((c) => ({ color: c.bandColor, title: c.tplName })),
      activityLine:
        (soloWinner?.state_delta?.["character.current_activity"] as string) ??
        (gap ? "—" : ""),
      onToggle: () => ctx.toggleGroup(g.actor_entity_id),
    };
  });
}

// ---------------------------------------------------------------------------
// Inspector
// ---------------------------------------------------------------------------

export function findSelectedTemplate(
  payload: ResolvePayload,
  sel: SelectionRef,
): { template: TemplatePayload | null; stack: StackPayload | null } {
  const g = payload.actors.find((a) => a.actor_entity_id === sel.actor);
  if (!g) return { template: null, stack: null };
  const inStack = (stack: StackPayload) =>
    stack.templates.find((t) => t.template_id === sel.tpl) ?? null;
  if (sel.kind === "solo" || sel.kind === "na") {
    const t = inStack(g.actor_stack);
    if (t) return { template: t, stack: g.actor_stack };
    return { template: null, stack: null };
  }
  const stacks =
    sel.kind === "pair" ? g.two_party_stacks : g.scene_pressure_stacks;
  const stack = stacks.find((s) => s.bindings.target === sel.target) ?? null;
  return { template: stack ? inStack(stack) : null, stack };
}

export function buildInspector(
  payload: ResolvePayload,
  sel: SelectionRef,
  opts: {
    hoverTag: string | null;
    naMarker?: { priority: number; drive_band: string } | null;
    blurbFor: (tpl: string) => string;
    branchesFor: (tpl: string) => { label: string; magnitude: number }[];
    ties: Map<string, string[]>;
  },
): InspectorVM | null {
  // Not-applicable rows have no evaluated stack entry; synthesize the header.
  if (sel.kind === "na") {
    const g = payload.actors.find((a) => a.actor_entity_id === sel.actor);
    const marker = g?.not_applicable.find((m) => m.template_id === sel.tpl);
    if (!marker) return null;
    return {
      name: marker.template_id,
      priority: marker.priority,
      bandColor: bandColor(marker.drive_band),
      tie: false,
      tieTitle: "",
      statusLabel: "not applicable — no target bound",
      statusTone: "na",
      bindingLine: `ACTOR ${g?.actor_name ?? sel.actor}`,
      blurb: opts.blurbFor(marker.template_id),
      isNA: true,
      gatePassed: false,
      gateRows: [],
      branches: [],
      fired: false,
      mag: "—",
      event: null,
      signalEvent: null,
      isPressure: false,
      pressureStub: "",
      deltaRows: [],
      bindingHash: "",
    };
  }

  const { template: t, stack } = findSelectedTemplate(payload, sel);
  if (!t || !stack) return null;
  const col = bandColor(t.drive_band);
  const status: RowStatus = rowStatus(t);
  const statusLabel =
    status === "winner"
      ? "winner"
      : status === "shadowed"
        ? "shadowed — fired, outranked"
        : "gate-failed — evaluated, refused";
  const tie = opts.ties.get(t.template_id) ?? null;

  const gateRows: InspectorVM["gateRows"] = [];
  const walk = (
    n: TraceNode,
    depth: number,
    onFail: boolean,
    negated: boolean,
  ) => {
    // Effective failure is polarity-aware, mirroring firstFailingLeaf: under
    // an odd number of enclosing NOTs, a *true* node is what blocks the gate.
    // Glyphs stay raw (the leaf's own truth); only emphasis/muting flips.
    const effFails = negated ? n.result : !n.result;
    if (!n.op) {
      const reads = evidenceReads(n.evidence);
      const failHere = onFail && effFails;
      gateRows.push({
        depth,
        isOp: false,
        glyph: n.result ? "✓" : "✗",
        glyphColor: n.result ? "hsl(var(--chart-5))" : "hsl(var(--destructive))",
        prose: n.prose,
        emphasized: failHere,
        muted: effFails && !failHere,
        evidence: evidenceText(n.evidence),
        evidenceHot: failHere,
        highlighted: !!opts.hoverTag && reads.includes(opts.hoverTag),
      });
      return;
    }
    gateRows.push({
      depth,
      isOp: true,
      glyph: n.result ? "✓" : "✗",
      glyphColor: n.result
        ? "hsl(var(--chart-5) / 0.7)"
        : "hsl(var(--destructive) / 0.8)",
      prose: n.op ?? "",
      emphasized: onFail && effFails,
      muted: !effFails,
      evidence: "",
      evidenceHot: false,
      highlighted: false,
    });
    // Under negation AND/OR swap culprit rules (De Morgan): a blocking
    // effective-AND implicates only its effectively-failing children; a
    // blocking effective-OR implicates all of them.
    const effOr = negated ? n.op === "AND" : n.op === "OR";
    for (const k of n.children ?? []) {
      const kidNegated = n.op === "NOT" ? !negated : negated;
      const kidEffFails = kidNegated ? k.result : !k.result;
      const kidOnFail =
        onFail && effFails && (n.op === "NOT" || kidEffFails || effOr);
      walk(k, depth + 1, kidOnFail, kidNegated);
    }
  };
  walk(t.gate_trace, 0, !t.gate_passed, false);

  // The explain payload traces branches only when the gate passed; for
  // refused gates, show the authored ladder from the catalog, all
  // unevaluated — matching the prototype's always-visible ladder.
  const branchSource: { label: string; magnitude: number; considered: boolean; result: boolean; selected: boolean; trace: TraceNode | null }[] =
    t.branches.length > 0
      ? t.branches
      : opts.branchesFor(t.template_id).map((b) => ({
          label: b.label,
          magnitude: b.magnitude,
          considered: false,
          result: false,
          selected: false,
          trace: null,
        }));
  const branches: InspectorVM["branches"] = branchSource.map((b, i) => {
    if (b.selected)
      return {
        idx: `B${i + 1}`,
        label: b.label,
        mag: b.magnitude.toFixed(2),
        selected: true,
        unevaluated: false,
        failed: false,
        note: "selected",
        noteGlyph: "◆",
        magColor: col,
      };
    if (b.considered && !b.result) {
      const fail = b.trace ? firstFailingLeaf(b.trace) : null;
      return {
        idx: `B${i + 1}`,
        label: b.label,
        mag: b.magnitude.toFixed(2),
        selected: false,
        unevaluated: false,
        failed: true,
        note: fail ? `${fail.prose} — ${fail.evidence}` : "condition failed",
        noteGlyph: "✗",
        magColor: "hsl(var(--muted-foreground))",
      };
    }
    if (b.considered && b.result && !b.selected)
      return {
        idx: `B${i + 1}`,
        label: b.label,
        mag: b.magnitude.toFixed(2),
        selected: false,
        unevaluated: false,
        failed: false,
        note: "passed — not sampled this tick",
        noteGlyph: "○",
        magColor: "hsl(var(--muted-foreground))",
      };
    return {
      idx: `B${i + 1}`,
      label: b.label,
      mag: b.magnitude.toFixed(2),
      selected: false,
      unevaluated: true,
      failed: false,
      note: t.gate_passed
        ? "unevaluated — a branch above already fired"
        : "unevaluated — gate refused",
      noteGlyph: "·",
      magColor: "hsl(var(--muted-foreground))",
    };
  });

  const targetName =
    sel.target != null ? (stack.binding_names.target ?? String(sel.target)) : null;
  return {
    name: t.template_id,
    priority: t.priority,
    bandColor: col,
    tie: !!tie,
    tieTitle: tie
      ? `priority ${t.priority} tied with ${tie.join(", ")} — BUILTIN_TEMPLATES tuple order decided`
      : "",
    statusLabel,
    statusTone:
      status === "winner" ? "winner" : status === "shadowed" ? "shadowed" : "failed",
    bindingLine: `ACTOR ${stack.binding_names.actor ?? sel.actor}${
      targetName ? `  ·  TARGET ${targetName}` : ""
    }${sel.kind === "pressure" ? "  ·  present-target pass" : ""}`,
    blurb: opts.blurbFor(t.template_id),
    isNA: false,
    gatePassed: t.gate_passed,
    gateRows,
    branches,
    fired: t.fired,
    mag: t.magnitude != null ? t.magnitude.toFixed(2) : "—",
    event: t.event_type,
    signalEvent: t.signal_event_type,
    isPressure: sel.kind === "pressure",
    pressureStub: t.scene_pressure_prompt_rendered ?? "",
    deltaRows: Object.entries(t.state_delta ?? {}).map(([k, v]) => ({
      k,
      v: Array.isArray(v) ? v.join(", ") : String(v),
    })),
    bindingHash: t.binding_hash,
  };
}

// ---------------------------------------------------------------------------
// Hover audit (entity context -> EntityAuditVM)
// ---------------------------------------------------------------------------

const NEED_ORDER = ["sleep", "thirst", "hunger", "socialize", "intimacy"];

export function buildEntityAudit(
  ent: ContextEntity,
  onScreen: boolean,
  hover: {
    onTagEnter: (tag: string) => void;
    onTagLeave: () => void;
  },
): EntityAuditVM {
  const needByType = new Map(ent.needs.map((n) => [n.need_type, n]));
  const needs = NEED_ORDER.map((nd) => {
    const row = needByType.get(nd);
    if (!row)
      return {
        nd,
        val: "immune",
        note: "",
        pct: "0%",
        color: "hsl(var(--muted-foreground) / 0.4)",
      };
    const sev = row.severity_name;
    const color =
      sev === "critical" || sev === "severe"
        ? "hsl(var(--destructive))"
        : sev === "moderate"
          ? "hsl(var(--chart-2))"
          : sev === "mild"
            ? "hsl(var(--chart-3))"
            : "hsl(var(--muted-foreground) / 0.6)";
    const pct = Math.min(100, Math.round(((row.severity_level ?? 0) / 4) * 100));
    return {
      nd,
      val: row.debt_score.toFixed(1),
      note: sev ?? "",
      pct: `${sev ? Math.max(pct, 8) : Math.min(99, Math.round(row.debt_score))}%`,
      color,
    };
  });

  const provenanceDot = (p: string) =>
    p === "exact" ? "●" : p === "approximate" ? "◍" : "○";
  const provenanceTitle = (row: { source_kind: string; provenance: string }) =>
    `${row.source_kind} · ${row.provenance}`;
  const mkTag = (row: ContextEntity["tags"]["durable"][number]) => ({
    name: row.tag,
    fam: row.families.length ? "◈" : "",
    famTitle: row.families.join(", ") || "no family",
    dot: provenanceDot(row.provenance),
    dotTitle: provenanceTitle(row),
    onEnter: () => hover.onTagEnter(row.tag),
    onLeave: () => hover.onTagLeave(),
  });

  const rels = ent.relationships.map((r) => ({
    types: r.relationship_type,
    other: r.other_name ?? String(r.other_entity_id),
    trust:
      r.valence_magnitude == null
        ? "—"
        : `${r.valence_magnitude >= 0 ? "+" : ""}${r.valence_magnitude}`,
  }));
  const knowledge = ent.knowledge.map((claim) => {
    const detail = [
      `#${claim.claim_id}`,
      claim.scope,
      claim.tier,
      claim.channel,
      claim.depth == null ? null : `depth ${claim.depth}`,
    ].filter((value): value is string => value != null);
    const immediate = claim.immediate_source?.name;
    const root = claim.root_source?.name;
    const provenance =
      immediate && root && immediate !== root
        ? `${immediate} ← root ${root}`
        : immediate ?? (root ? `root ${root}` : "universal / direct");
    return {
      key: String(claim.claim_id),
      summary: claim.summary,
      meta: detail.join(" · "),
      provenance,
      acquired: claim.acquired_at_world_time ?? "world time unstamped",
    };
  });
  const events = ent.recent_events.map((ev) => ({
    t: `t${String(ev.tick_chunk_id).padStart(4, "0")}`,
    type: ev.event_type,
  }));

  return {
    name: ent.name,
    place: ent.place?.name ?? "—",
    classes: ent.place?.classes.join(" · ") ?? "",
    fameRes: onScreen ? "on-screen" : "off-screen",
    needs,
    durable: ent.tags.durable.map(mkTag),
    ephemeral: ent.tags.ephemeral.map(mkTag),
    hasEphemeral: ent.tags.ephemeral.length > 0,
    rels,
    hasRels: rels.length > 0,
    knowledge,
    hasKnowledge: knowledge.length > 0,
    events,
    hasEvents: events.length > 0,
  };
}

// ---------------------------------------------------------------------------
// Rail / summary helpers
// ---------------------------------------------------------------------------

export function winnersByBand(payload: ResolvePayload): Record<string, number> {
  const counts: Record<string, number> = Object.fromEntries(
    BAND_ORDER.map((b) => [b, 0]),
  );
  for (const g of payload.actors) {
    const bump = (stack: StackPayload) => {
      const w = stack.templates.find((t) => t.is_winner);
      if (w) counts[w.drive_band] = (counts[w.drive_band] ?? 0) + 1;
    };
    bump(g.actor_stack);
    g.two_party_stacks.forEach(bump);
    g.scene_pressure_stacks.forEach(bump);
  }
  counts.embodied_maintenance += payload.need_pressures.length;
  return counts;
}

export function priorityTies(
  ties: { template_ids: string[] }[],
): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const tie of ties) {
    for (const id of tie.template_ids) {
      map.set(
        id,
        tie.template_ids.filter((other) => other !== id),
      );
    }
  }
  return map;
}
