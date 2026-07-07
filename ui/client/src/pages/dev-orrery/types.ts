// Payload types for /api/dev/orrery/* (mirrors nexus/agents/orrery/audit.py
// and orrery_dev_endpoints.py) plus the view-model shapes the design
// prototype's components render. The adapter between them lives in vm.ts.

// ---------------------------------------------------------------------------
// API payloads
// ---------------------------------------------------------------------------

export interface TraceEvidence {
  kind: string;
  params: Record<string, unknown>;
  entities: Record<string, number | null>;
  observed: Record<string, unknown>;
  matched: unknown[] | null;
  result: boolean | null;
}

export interface TraceNode {
  raw: string;
  prose: string;
  result: boolean;
  op?: "AND" | "OR" | "NOT";
  children?: TraceNode[];
  evidence?: TraceEvidence | null;
}

export interface BranchTracePayload {
  label: string;
  magnitude: number;
  considered: boolean;
  result: boolean;
  selected: boolean;
  trace: TraceNode | null;
}

export interface TemplatePayload {
  template_id: string;
  priority: number;
  drive_band: string;
  blurb: string;
  required_slots: string[];
  present_target_policy: string;
  gate_passed: boolean;
  gate_trace: TraceNode;
  fired: boolean;
  chosen_branch: string | null;
  branches: BranchTracePayload[];
  magnitude: number | null;
  event_type: string | null;
  signal_event_type: string | null;
  narrative_stub: string | null;
  narrative_stub_rendered: string | null;
  scene_pressure_prompt_rendered: string | null;
  binding_hash: string;
  state_delta: Record<string, unknown>;
  changed_fields: string[];
  is_winner: boolean;
  is_shadowed: boolean;
}

export interface StackDiff {
  changed: boolean;
  baseline_winner_id: string | null;
  baseline_chosen_branch: string | null;
  baseline_magnitude: number | null;
  changed_template_ids: string[];
}

export interface StackPayload {
  bindings: Record<string, number>;
  binding_names: Record<string, string>;
  winner_id: string | null;
  shadowed_ids: string[];
  templates: TemplatePayload[];
  diff: StackDiff | null;
}

export interface NotApplicableMarker {
  template_id: string;
  priority: number;
  drive_band: string;
  reason: string;
}

export interface ActorGroupPayload {
  actor_entity_id: number;
  actor_name: string;
  location: { place_id: number; name: string | null } | null;
  activity: string | null;
  actor_stack: StackPayload;
  two_party_stacks: StackPayload[];
  scene_pressure_stacks: StackPayload[];
  not_applicable: NotApplicableMarker[];
}

export interface NeedPressurePayload {
  template_id: string;
  priority: number;
  binding_hash: string;
  bindings: Record<string, number>;
  branch_label: string;
  pressure_stub: string;
  prompt_text: string;
  magnitude: number;
}

export interface JointBeatPayload {
  kind: "reciprocal" | "crossed";
  entity_a: number;
  entity_b: number;
  forward_proposal_id: string;
  reverse_proposal_id: string;
  forward_template_id: string;
  reverse_template_id: string;
  forward_stub: string;
  reverse_stub: string;
  magnitude: number;
  entity_names: Record<string, string>;
}

export interface ResolvePayload {
  anchor_chunk_id: number | null;
  window_chunks: number;
  world_time: string | null;
  time_of_day: string;
  weather: string;
  actor_count: number;
  mode: "current" | "what_if";
  overrides: Record<string, unknown> | null;
  generated_at: string;
  actors: ActorGroupPayload[];
  joint_beats: JointBeatPayload[];
  need_pressures: NeedPressurePayload[];
  need_pressures_diff: {
    added: NeedPressurePayload[];
    removed: NeedPressurePayload[];
    changed: { current: NeedPressurePayload; baseline: NeedPressurePayload }[];
  } | null;
  entity_names: Record<string, string>;
}

// --- what-if override request shapes (mirror OrreryOverridesModel) ---------

export interface TagOverride {
  entity_id: number;
  tag: string;
  op: "add" | "remove";
  ephemeral: boolean;
}
export interface PairTagOverride {
  subject_entity_id: number;
  object_entity_id: number;
  tag: string;
  op: "add" | "remove";
}
export interface NeedOverride {
  entity_id: number;
  need_type: string;
  debt_score: number;
}
export interface LocationOverride {
  entity_id: number;
  place_id: number;
}
export interface EventOverride {
  event_type: string;
  actor_entity_id?: number | null;
  target_entity_id?: number | null;
  ticks_ago?: number;
}
export interface OverridesRequest {
  tags: TagOverride[];
  pair_tags: PairTagOverride[];
  needs: NeedOverride[];
  locations: LocationOverride[];
  events: EventOverride[];
}
/** One override plus the chip label shown under the tick bar. */
export interface OverrideChipEntry {
  label: string;
  patch: Partial<OverridesRequest>;
}

// --- catalog ----------------------------------------------------------------

export interface CatalogTemplate {
  template_id: string;
  priority: number;
  tuple_index: number;
  drive_band: string;
  blurb: string;
  required_slots: string[];
  arity: "actor_only" | "two_party";
  present_target_policy: string;
  priority_override_rationale: string | null;
  branches: {
    label: string;
    magnitude: number;
    event_type: string | null;
    signal_event_type: string | null;
  }[];
  consumed_event_types: { gate: string[]; branch: string[] };
  emitted_event_types: string[];
}

export interface CatalogPayload {
  drive_bands: { band: string; urgency_rank: number; templates: CatalogTemplate[] }[];
  pseudo_templates: { template_id: string; need_type: string; priority: number }[];
  tag_families: Record<string, { kind: string; members: string[] }>;
  event_map: Record<
    string,
    {
      consumed_by_gate: string[];
      consumed_by_branch: string[];
      emitted_by: string[];
      exogenous_only: boolean;
    }
  >;
  priority_ties: { arity: string; priority: number; template_ids: string[] }[];
  promotion: { priority_threshold: number; magnitude_threshold: number } | null;
}

// --- entity context (hover audit) -------------------------------------------

export interface ContextTagRow {
  tag: string;
  category: string;
  is_ephemeral: boolean;
  source_kind: string;
  applied_at_world_time: string | null;
  source_chunk_id: number | null;
  provenance: "exact" | "approximate" | "unknowable";
  families: string[];
}

export interface ContextEntity {
  entity_id: number;
  name: string;
  kind: string | null;
  place: {
    place_id: number;
    name: string | null;
    place_type: string | null;
    classes: string[];
  } | null;
  activity: string | null;
  needs: {
    need_type: string;
    debt_score: number;
    severity_level: number | null;
    severity_name: string | null;
  }[];
  tags: { durable: ContextTagRow[]; ephemeral: ContextTagRow[] };
  pair_tags: {
    tag: string;
    direction: "outbound" | "inbound";
    other_entity_id: number;
    other_name?: string;
    provenance: string;
  }[];
  relationships: {
    relationship_type: string;
    valence_magnitude: number | null;
    direction: "outbound" | "inbound";
    other_entity_id: number;
    other_name?: string;
    versioned: boolean;
  }[];
  recent_events: {
    event_type: string;
    tick_chunk_id: number;
    actor_name: string | null;
    target_name: string | null;
  }[];
}

export interface ContextPayload {
  anchor_chunk_id: number | null;
  world_time: string | null;
  entities: ContextEntity[];
}

// --- coverage ----------------------------------------------------------------

export interface CoveragePayload {
  anchor_chunk_ids: number[];
  anchors: {
    anchor_chunk_id: number;
    winners_by_band: Record<string, number>;
    gap_actor_ids: number[];
    need_pressure_count: number;
  }[];
  templates: Record<
    string,
    {
      drive_band: string;
      evaluated: number;
      fired: number;
      won: number;
      pressure_fired: number;
      pressure_won: number;
    }
  >;
  never_fired: string[];
  fired_never_won: string[];
  always_won_when_fired: string[];
  gap_actors: {
    entity_id: number;
    name: string | null;
    seen_anchors: number;
    gapped_anchors: number;
  }[];
  dead_gate_arms: Record<
    string,
    { consumed_by_gate: string[]; consumed_by_branch: string[] }
  >;
  data_quality: {
    null_world_time_bestowals: {
      bestowal_table: string;
      source_kind: string;
      null_world_time_rows: number;
      active_rows: number;
    }[];
    wall_clock_epochs: {
      bestowal_table: string;
      wall_clock_instant: string;
      rows: number;
      distinct_world_times: number;
    }[];
  };
  hydration_honesty: Record<string, string[]>;
}

// --- vocab -------------------------------------------------------------------

export interface VocabPayload {
  tags: { tag: string; category: string; is_ephemeral: boolean }[];
  pair_tags: { tag: string; subject_kinds: string[]; object_kinds: string[] }[];
  event_types: { type: string; category: string | null }[];
  places: { id: number; name: string }[];
}

// ---------------------------------------------------------------------------
// View models (the shapes the design components render)
// ---------------------------------------------------------------------------

/** GateBrackets / inspector tree node. */
export interface EvaluatedGateNode {
  kind: "leaf" | "op";
  op?: "AND" | "OR" | "NOT";
  pass: boolean;
  prose: string;
  evidence: string;
  reads: string[];
  children?: EvaluatedGateNode[];
}

export interface MagChip {
  dial: boolean;
  deg?: number;
  color: string;
  text: string;
}

export interface ResolutionCardVM {
  key: string;
  kind: "solo" | "pair";
  tplName: string;
  priority: string;
  bandColor: string;
  dim: boolean;
  tie: boolean;
  tieTitle: string;
  isPair: boolean;
  targetName: string | null;
  targetEntityId: number | null;
  branchLabel: string;
  event: string | null;
  mag: MagChip | null;
  selected: boolean;
  diff: boolean;
  highlight: boolean;
  dimByLens: boolean;
  pad: number;
  shadowCount: number;
  hasShadow: boolean;
  shadowOpen: boolean;
  shadowed: ResolutionCardVM[];
  onSelect: () => void;
  onToggleShadow?: () => void;
}

export interface EntityAuditVM {
  name: string;
  place: string;
  classes: string;
  fameRes: string;
  needs: { nd: string; val: string; note: string; pct: string; color: string }[];
  durable: EntityAuditTagVM[];
  ephemeral: EntityAuditTagVM[];
  hasEphemeral: boolean;
  rels: { types: string; other: string; trust: string }[];
  hasRels: boolean;
  events: { t: string; type: string }[];
  hasEvents: boolean;
}

export interface EntityAuditTagVM {
  name: string;
  fam: string;
  famTitle: string;
  dot: string;
  dotTitle: string;
  onEnter?: () => void;
  onLeave?: () => void;
}

export type RowStatus = "winner" | "shadowed" | "gate_failed" | "not_applicable";

export interface GhostRowVM {
  key: string;
  name: string;
  glyph: string;
  status: RowStatus;
  reason: string;
  evidence: string;
  na: boolean;
  selected: boolean;
  onSelect: () => void;
}

export interface PressureChipVM {
  key: string;
  label: string;
  title: string;
  selected: boolean;
  diff: boolean;
  onSelect: () => void;
}

export interface ActorGroupVM {
  id: number;
  domId: string;
  name: string;
  initials: string;
  ringColor: string;
  placeName: string;
  open: boolean;
  gap: boolean;
  diff: boolean;
  cards: ResolutionCardVM[];
  pressures: PressureChipVM[];
  ghosts: GhostRowVM[];
  bandDots: { color: string; title: string }[];
  activityLine: string;
  onToggle: () => void;
}

export interface SelectionRef {
  key: string;
  actor: number;
  target: number | null;
  tpl: string;
  kind: "solo" | "pair" | "pressure" | "na";
}

export interface InspectorGateRowVM {
  depth: number;
  isOp: boolean;
  glyph: string;
  glyphColor: string;
  prose: string;
  emphasized: boolean;
  muted: boolean;
  evidence: string;
  evidenceHot: boolean;
  highlighted: boolean;
}

export interface InspectorBranchVM {
  idx: string;
  label: string;
  mag: string;
  selected: boolean;
  unevaluated: boolean;
  failed: boolean;
  note: string;
  noteGlyph: string;
  magColor: string;
}

export interface InspectorVM {
  name: string;
  priority: number;
  bandColor: string;
  tie: boolean;
  tieTitle: string;
  statusLabel: string;
  statusTone: "winner" | "shadowed" | "failed" | "na";
  bindingLine: string;
  blurb: string;
  isNA: boolean;
  gatePassed: boolean;
  gateRows: InspectorGateRowVM[];
  branches: InspectorBranchVM[];
  fired: boolean;
  mag: string;
  event: string | null;
  signalEvent: string | null;
  isPressure: boolean;
  pressureStub: string;
  deltaRows: { k: string; v: string }[];
  bindingHash: string;
}
