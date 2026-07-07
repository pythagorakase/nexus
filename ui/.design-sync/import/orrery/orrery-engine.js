/*
 * orrery-engine.js — seeded, deterministic mini-implementation of the Orrery
 * off-screen resolver + explain layer, for the audit-dashboard prototype.
 *
 * Ground truth: docs/orrery_packages.md @ aaa854ee (all 25 BUILTIN_TEMPLATES:
 * priorities, gates, branches, magnitudes, narrative stubs verbatim) and
 * nexus/agents/orrery/needs.py (5 needs, severity thresholds, pressure tuning).
 * Family tag sets are approximations of substrate.py frozensets (marked ~).
 *
 * Everything is pure: resolveTick(state) -> explained payload. No RNG.
 */

// ---------------------------------------------------------------- vocab ----

export const BANDS = [
  { id: 'crisis',   name: 'Crisis / Constraint',     chart: 1 },
  { id: 'embodied', name: 'Embodied Maintenance',    chart: 2 },
  { id: 'routine',  name: 'Anchored Routine',        chart: 3 },
  { id: 'affil',    name: 'Affiliation',             chart: 4 },
  { id: 'project',  name: 'Project / Identity',      chart: 5 },
];

export const FAME = ['unknown', 'local', 'known', 'renowned', 'legendary'];
export const RESOURCES = ['destitute', 'poor', 'struggling', 'comfortable', 'wealthy', 'magnate'];

export const NEEDS = ['sleep', 'hunger', 'thirst', 'socialize', 'intimacy'];
export const NEED_THRESHOLDS = {
  sleep:     { mild: 16, moderate: 30, severe: 48,  critical: 72 },
  hunger:    { mild: 8,  moderate: 16, severe: 30,  critical: 48 },
  thirst:    { mild: 4,  moderate: 8,  severe: 16,  critical: 24 },
  socialize: { mild: 24, moderate: 72, severe: 168, critical: 336 },
  intimacy:  { mild: 72, moderate: 168, severe: 336, critical: 720 },
};
export const NEED_PRESSURE_PRIORITY = { sleep: 25, thirst: 24, hunger: 22, socialize: 18, intimacy: 16 };
export const NEED_IMMUNITY = {
  sleep:  ['bodyform:android', 'bodyform:construct', 'digital_mind', 'inorganic', 'virtual'],
  hunger: ['bodyform:android', 'bodyform:construct', 'digital_mind', 'inorganic', 'virtual'],
  thirst: ['bodyform:android', 'bodyform:construct', 'digital_mind', 'inorganic', 'virtual'],
  socialize: [],
  intimacy: ['digital_mind', 'libido_absent', 'virtual'],
};

// ~approximations of substrate.py curated frozensets
export const FAMILIES = {
  INTIMACY_SUPPRESSOR_TAGS: ['grudge_active', 'distressed', 'cns_stimulated', 'at_vigil'],
  HIDDEN_TAGS: ['off_grid', 'undercover', 'cover_identity', 'fugitive'],
  CONSTRAINED_TAGS: ['captive', 'unconscious', 'dying'],
  PUBLIC_MOBILITY_BLOCKERS: ['off_grid', 'fugitive', 'wanted', 'captive', 'unconscious'],
  DRAMATIC_CONTACT_TAGS: ['off_grid', 'undercover', 'cover_identity', 'fugitive', 'wanted'],
};
export function familiesOf(tag) {
  return Object.keys(FAMILIES).filter((f) => FAMILIES[f].includes(tag));
}

export const PLACES = {
  rootline:    { id: 'rootline',    name: 'The Rootline — Sublevel Nine',   classes: ['subterranean', 'transit'] },
  glow:        { id: 'glow',        name: 'The Glow — Market Concourse',    classes: ['commerce', 'meeting', 'place_open', 'urban_dense'] },
  stacks:      { id: 'stacks',      name: 'The Stacks — Fabrication Row',   classes: ['craft', 'place_restricted', 'production'] },
  remembrance: { id: 'remembrance', name: 'The Remembrance Yard',           classes: ['sacred', 'tomb'] },
  ashgrid:     { id: 'ashgrid',     name: 'Ash-Grid Safehouse',             classes: ['haven', 'dwelling'] },
};

// ------------------------------------------------------- condition DSL ----

const A = (...children) => ({ op: 'AND', children });
const O = (...children) => ({ op: 'OR', children });
const N = (child) => ({ op: 'NOT', children: [child] });
const L = (p, args = {}, prose = '') => ({ p, ...args, prose });

// Leaf builders (prose matches catalog rendering)
const hydrated   = (w = 'actor') => L('hydrated', { w }, `${w} has enough hydrated context`);
const tag        = (w, t) => L('tag', { w, t }, `${w} has \`${t}\` tag`);
const eph        = (w, t) => L('eph', { w, t }, `${w} has \`${t}\` ephemeral`);
const anyTag     = (w, list, label) => L('anyTag', { w, list }, label || `${w} has any of [${list.map((x) => '`' + x + '`').join(', ')}]`);
const anyCur     = (w, list) => L('anyCur', { w, list }, `${w} has any current tag of [${list.map((x) => '`' + x + '`').join(', ')}]`);
const inPair     = (w, t) => L('inPair', { w, t }, `${w} has inbound \`${t}\` pair tag`);
const outPair    = (w, t) => L('outPair', { w, t }, `${w} has outbound \`${t}\` pair tag`);
const residesHere = () => L('residesHere', {}, 'actor has `resides_at` pair tag to current location');
const relShared  = (t) => L('relShared', { t }, `actor and target share \`${t}\` relationship (either direction)`);
const relDir     = (t) => L('relDir', { t }, `actor has \`${t}\` relationship to target`);
const trustLt    = (v) => L('trustLt', { v }, `trust actor→target < ${v}`);
const trustGte   = (v) => L('trustGte', { v }, `trust actor→target ≥ ${v}`);
const mutualWarm = () => L('mutualWarm', {}, 'actor and target have mutual warm trust');
const trustLoaded = () => L('trustLoaded', {}, 'directional trust actor↔target differs by 3+ or is loaded');
const dramatic   = () => L('dramatic', {}, 'direct contact actor→target is dramatic');
const need       = (nd, v) => L('need', { nd, v }, `actor has \`${nd}\` debt ≥ ${v}`);
const evRecent   = (t, targeting, within) => L('evRecent', { t, targeting, within },
  targeting === 'any' ? `recent \`${t}\` event in last ${within} ticks` : `recent \`${t}\` event targeting ${targeting} in last ${within} ticks`);
const cooldown   = (t, scope, ticks) => L('cooldown', { t, scope, ticks },
  `≥ ${ticks} ticks since last \`${t}\` event for ${scope === 'pair' ? '(actor, target) pair' : 'actor'}`);
const tod        = (list) => L('tod', { list }, `time of day is one of [${list.join(', ')}]`);
const weather    = (list) => L('weather', { list }, `weather is one of [${list.join(', ')}]`);
const place      = (w, c) => L('place', { w, c }, `${w} is in \`${c}\` place class`);
const colo       = () => L('colo', {}, 'actor and target are co-located');
const othersColo = (n, w = 'actor') => L('othersColo', { n, w }, `${n}+ other entities co-located with ${w}`);
const othersGrieving = () => L('othersGrieving', {}, '1+ other entities with `grieving` ephemeral co-located with actor');
const fameGte    = (r) => L('fameGte', { r }, `actor's own fame is \`${r}\` or wider`);
const fameLt     = (r) => L('fameLt', { r }, `actor's own fame is narrower than \`${r}\``);
const resGte     = (r) => L('resGte', { r }, `actor's own resources are \`${r}\` or better`);
const resLt     = (r) => L('resLt', { r }, `actor's own resources are below \`${r}\``);
const constrained = () => L('constrained', {}, 'actor is constrained or immobilized');
const hiddenOff  = () => L('hiddenOff', {}, 'actor is hidden or off-grid');
const pubFlow    = (w = 'actor') => L('pubFlow', { w }, `${w} can plausibly move through public flow`);
const intimSupp  = () => L('intimSupp', {}, 'actor has an intimacy suppressor');
const inTransit  = () => L('inTransit', {}, 'actor is in transit');
const hasDest    = () => L('hasDest', {}, 'actor has a planned travel destination');
const travProg   = (v) => L('travProg', { v }, `actor travel progress ≥ ${v}`);
const travPurpose = (v) => L('travPurpose', { v }, `actor is traveling for \`${v}\` purpose`);
const travRisk   = (list) => L('travRisk', { list }, `actor travel risk is one of [${list.join(', ')}]`);
const anchorHas  = (k) => L('anchorHas', { k }, `actor has \`${k}\` routine anchor`);
const anchorDue  = (k) => L('anchorDue', { k }, `actor's \`${k}\` routine is due now (weekdays 0=Monday; empty schedule always due)`);
const anchorAway = (k) => L('anchorAway', { k }, `actor is away from \`${k}\` anchor`);
const anchorAt   = (k) => L('anchorAt', { k }, `actor is at \`${k}\` anchor`);
const anchorResolves = (k) => L('anchorResolves', { k }, `actor's \`${k}\` routine can resolve a destination`);
const partnerColo = () => L('partnerColo', {}, 'actor has an established partner co-located');
const factionSenior = () => L('factionSenior', {}, 'actor holds `status:senior`+ toward any faction');
const resolveDest = (classes) => L('resolveDest', { classes }, `actor can resolve a destination with place class \`${classes.join(',')}\``);
const ALWAYS = null;

// --------------------------------------------------------- the catalog ----
// Order = BUILTIN_TEMPLATES authored tuple order (priority desc; ties broken
// by this order — CULTIVATE_INFORMANT before KEEP_VIGIL, MOURN_LOSS before SLEEP).

const CRAFT_TAGS = ['combat_trained', 'soldier', 'warrior', 'fighter', 'arcane_caster', 'engineer', 'mechanic', 'tinkerer', 'hacker', 'artificer', 'musician', 'dancer', 'performer', 'artist', 'writer', 'artisan', 'athlete', 'martial_artist', 'ranger', 'scout', 'monk', 'keeps_shop', 'merchant', 'innkeeper', 'trader', 'domestic_role', 'cares_for_household', 'matriarch', 'patriarch', 'scholar', 'researcher', 'academic', 'loremaster'];

export const TEMPLATES = [
  {
    id: 'EVADE_PURSUERS', tid: 'evade_pursuers', band: 'crisis', priority: 100, slots: ['ACTOR'], ptp: false,
    blurb: 'When the city is closing in.',
    gate: A(
      O(inPair('actor', 'hunting'), evRecent('compliance_alert', 'actor', 5)),
      N(constrained()),
      O(A(place('actor', 'subterranean'), place('actor', 'transit')), outPair('actor', 'contact:lodging'), pubFlow()),
    ),
    branches: [
      { label: 'Go to ground in flooded tunnels', mag: 0.72, when: A(A(place('actor', 'subterranean'), place('actor', 'transit')), weather(['rain'])),
        does: 'activity → "hiding from active pursuit"; adds `off_grid` to actor', event: 'evade_pursuit',
        delta: { 'character.current_activity': 'hiding from active pursuit', 'entity_tags.add': ['off_grid'] },
        stub: '{actor} slips off a Rootline platform into a flooded service corridor and kills every transmitter on their person.' },
      { label: 'Buy a discreet extraction', mag: 0.64, when: A(fameGte('renowned'), resGte('wealthy')),
        does: 'activity → "buying a discreet extraction"', event: 'evade_pursuit',
        delta: { 'character.current_activity': 'buying a discreet extraction' },
        stub: '{actor} knows their face does half the pursuers\u2019 work for them, so they pay for the kind of exit that never touches public flow: a closed vehicle, a bought route, a driver whose business is not remembering.' },
      { label: 'Reach a safe house through contacts', mag: 0.58, when: outPair('actor', 'contact:lodging'),
        does: 'activity → "relocating through safe contacts"', event: 'evade_pursuit',
        delta: { 'character.current_activity': 'relocating through safe contacts' },
        stub: '{actor} pings a broker through a low-bandwidth dead-drop and takes a four-hop route to a safe house.' },
      { label: 'Keep moving, blend into public flow', mag: 0.42, when: A(pubFlow(), fameLt('renowned')),
        does: 'activity → "blending into public flow"', event: 'evade_pursuit',
        delta: { 'character.current_activity': 'blending into public flow' },
        stub: '{actor} joins the densest pedestrian current nearby, never stopping long enough to make a clean pattern.' },
      { label: 'Break line of sight without a clean route', mag: 0.28, when: ALWAYS,
        does: 'activity → "breaking pursuit pattern"', event: 'evade_pursuit',
        delta: { 'character.current_activity': 'breaking pursuit pattern' },
        stub: '{actor} cannot rely on a clean public path, so they buy seconds instead: doors, stairwells, service gaps, and any angle that keeps the pursuit from becoming certain.' },
    ],
  },
  {
    id: 'PROTECT_KIN', tid: 'protect_kin', band: 'crisis', priority: 95, slots: ['ACTOR', 'TARGET'], ptp: true,
    blurb: 'A bond pulls the actor toward someone in active danger.',
    gate: A(
      O(relShared('family'), relShared('romantic'), relShared('chosen_kin'), relShared('comrade')),
      O(inPair('target', 'hunting'), eph('target', 'wounded'), evRecent('threat_issued', 'target', 4)),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Physically intervene at the target\u2019s location', mag: 0.78, when: A(colo(), inPair('target', 'hunting')),
        does: 'activity → "shielding kin from active threat"; adds `recently_protective` to actor; clears inbound `hunting` pair tags from target', event: 'protective_intervention',
        delta: { 'character.current_activity': 'shielding kin from active threat', 'entity_tags.add': ['recently_protective'], 'pair_tags.clear': ['hunting → target'] },
        stub: '{actor} reaches {target} as the noose tightens — pulling them off the line of sight, into a service corridor whose layout {actor} has memorized for exactly this kind of moment.',
        pressure: '{actor} may be close enough to intervene around {target}\u2019s current danger. Treat this as potential off-screen support or complication for the scene, not as an automatic rescue.' },
      { label: 'Travel toward the target\u2019s last known location', mag: 0.52, when: A(outPair('actor', 'contact:social'), N(colo())),
        does: 'activity → "moving to reach kin in danger"', event: 'protective_intervention',
        delta: { 'character.current_activity': 'moving to reach kin in danger' },
        stub: '{actor} drops what they were doing and starts moving — calling in favors at every transit checkpoint to shave minutes off the route to {target}, knowing the minutes might matter.',
        pressure: '{actor} is moving toward {target}\u2019s current location because they believe the danger is real. You may foreshadow, delay, or ignore their arrival based on the active scene.' },
      { label: 'Signal kin networks to converge on the target', mag: 0.41, when: relShared('comrade'),
        does: 'activity → "coordinating kin response"', event: 'protective_intervention',
        delta: { 'character.current_activity': 'coordinating kin response' },
        stub: '{actor} pushes a coded distress beacon through the kin network — the kind of signal that pulls three or four people toward {target} from different directions without coordination.',
        pressure: '{actor} has signaled a kin network around {target}. This can become outside help, cross-traffic, noise, or a looming option if it fits the live scene.' },
      { label: 'Maintain vigil and wait for resolution', mag: 0.22, when: ALWAYS,
        does: 'activity → "waiting on news of kin"; adds `distressed` to actor', event: 'protective_intervention',
        delta: { 'character.current_activity': 'waiting on news of kin', 'entity_tags.add': ['distressed'] },
        stub: '{actor} can\u2019t reach {target} in time, can\u2019t call who they would need to call — and stays close to a comm, monitoring channels, waiting for the news that will determine what comes next.',
        pressure: '{actor} is monitoring {target}\u2019s danger from off-screen. This is emotional and logistical pressure, not a command to change what {target} does in the scene.' },
    ],
  },
  {
    id: 'EXTRACT_VENGEANCE', tid: 'extract_vengeance', band: 'project', priority: 90, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Active vengeance is a high-pressure identity project; left alone, it should interrupt ordinary life.',
    blurb: 'A grudge ripens until the moment is right to settle it.',
    gate: A(
      eph('actor', 'grudge_active'),
      O(relShared('enemy'), relShared('rival'), trustLt(-2)),
      cooldown('retaliation_attempted', 'actor', 8),
      cooldown('retaliation_executed', 'actor', 8),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Strike directly when opportunity opens', mag: 0.85, when: A(colo(), N(othersColo(2, 'target')), anyTag('actor', ['vendetta_holder', 'violent_history'])),
        does: 'activity → "executing retaliation"; adds `recently_violent` to actor; removes `grudge_active`', event: 'retaliation_executed',
        delta: { 'character.current_activity': 'executing retaliation', 'entity_tags.add': ['recently_violent'], 'entity_tags.clear': ['grudge_active'] },
        stub: '{actor} moves on {target} in the moment the corridor clears — no warning, no negotiation, the years of waiting compressed into the time it takes to close a few meters of distance.',
        pressure: '{actor}\u2019s grudge is close enough to {target}\u2019s current scene to become immediate pressure. Treat it as a possible threat, interruption, warning sign, or delayed consequence rather than an automatic attack.' },
      { label: 'Surface a reputation attack in the right channels', mag: 0.58, when: A(outPair('actor', 'contact:social'), O(place('actor', 'urban_dense'), place('actor', 'commerce'), place('actor', 'meeting'))),
        does: 'activity → "running a reputation attack"; adds `reputation_compromised` to target', event: 'retaliation_attempted',
        delta: { 'character.current_activity': 'running a reputation attack', 'entity_tags.add': ['reputation_compromised → target'] },
        stub: '{actor} feeds a curated dossier on {target} into three brokers in the Glow, taking pains to make the leak look like an accident of incautious clients rather than deliberate sabotage.',
        pressure: '{actor} is trying to compromise {target}\u2019s reputation through off-screen channels. If useful, let the current scene show a rumor, message, social consequence, or pressure wave instead of a direct state change.' },
      { label: 'Watch and document, waiting for a better window', mag: 0.34, when: ALWAYS,
        does: 'activity → "surveilling a grudge target"', event: 'retaliation_attempted',
        delta: { 'character.current_activity': 'surveilling a grudge target' },
        stub: '{actor} continues to observe {target}\u2019s patterns from cover — shift changes, contacts, the geometry of their movements — letting the grudge stay sharp without spending it prematurely.',
        pressure: '{actor} is watching {target}\u2019s current patterns from cover. This can surface as unease, surveillance traces, or a later setup, but {target}\u2019s on-screen choices remain yours.' },
    ],
  },
  {
    id: 'TEND_WOUNDED', tid: 'tend_wounded', band: 'crisis', priority: 88, slots: ['ACTOR', 'TARGET'], ptp: true,
    blurb: 'A wounded body pulls the actor toward the small work of mending.',
    gate: A(
      eph('target', 'wounded'),
      colo(),
      N(inPair('actor', 'hunting')),
      N(inPair('target', 'hunting')),
      cooldown('tended_wound', 'pair', 2),
      cooldown('wound_healed', 'pair', 2),
    ),
    branches: [
      { label: 'Channel restorative power through hands and voice', mag: 0.74, when: tag('actor', 'magical_healing'),
        does: 'activity → "channeling restorative power"; removes `wounded` from target', event: 'wound_healed',
        delta: { 'character.current_activity': 'channeling restorative power', 'entity_tags.clear': ['wounded → target'], 'entity_tags.add': ['recently_drained'] },
        stub: '{actor} kneels beside {target} and places hands where the damage lives. Something passes between them — a quiet exchange of warmth and pain — and the body begins to remember how to be whole.',
        pressure: '{actor} may be close enough to attempt restorative work on {target}\u2019s wound in the active scene. Treat as offered help the scene can accept, defer, or complicate, not as automatic healing.' },
      { label: 'Work the wound with trained hands', mag: 0.58, when: anyTag('actor', ['surgical_training', 'medical_skill']),
        does: 'activity → "providing skilled medical care"; removes `wounded` from target; adds `recently_tended` to target', event: 'tended_wound',
        delta: { 'character.current_activity': 'providing skilled medical care', 'entity_tags.clear': ['wounded → target'], 'entity_tags.add': ['recently_tended → target'] },
        stub: '{actor} cleans the wound by feel, finds what needs to be found, and does the work the body cannot do for itself. {target} watches the ceiling and counts something silently.',
        pressure: '{actor} is moving to provide skilled medical care to {target}. The scene may show this as a quiet competent interruption, a wait for stabilization, or a beat of trust between them.' },
      { label: 'Apply what first-aid the moment allows', mag: 0.42, when: tag('actor', 'first_aid_trained'),
        does: 'activity → "applying field first aid"; adds `recently_tended` to target', event: 'tended_wound',
        delta: { 'character.current_activity': 'applying field first aid', 'entity_tags.add': ['recently_tended → target'] },
        stub: '{actor} works from memory — pressure here, elevation there, the things that buy time when time is the thing you need. It won\u2019t be enough on its own, but it\u2019s enough for now.',
        pressure: '{actor} has practical first-aid training and is at {target}\u2019s side. Treat as a stabilizing presence the scene can use without granting full recovery.' },
      { label: 'Stay with the wound and do what can be done', mag: 0.24, when: ALWAYS,
        does: 'activity → "keeping watch over the wounded"', event: 'tended_wound',
        delta: { 'character.current_activity': 'keeping watch over the wounded' },
        stub: '{actor} has no real skill for this. They press a cloth where there is bleeding and speak softly so {target} has a voice to follow back from wherever the body has gone.',
        pressure: '{actor} is present at {target}\u2019s side without medical ability. Use this as accompaniment and witness — not as intervention.' },
    ],
  },
  {
    id: 'HIDE', tid: 'hide', band: 'crisis', priority: 84, slots: ['ACTOR'], ptp: false,
    blurb: 'Steady-state concealment for people who are already living out of sight.',
    gate: A(
      hydrated(),
      hiddenOff(),
      N(inPair('actor', 'hunting')),
      N(constrained()),
      cooldown('hideout_maintained', 'actor', 6),
      cooldown('signal_exposure_reduced', 'actor', 6),
      cooldown('counter_surveillance_sweep', 'actor', 6),
    ),
    branches: [
      { label: 'Erase the identity and vanish completely', mag: 0.62, when: A(fameGte('legendary'), resGte('magnate')),
        does: 'activity → "erasing their identity"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'erasing their identity' },
        stub: '{actor} is too widely known to be hidden by walls or habits, so they spend what almost no one can spend: the records, the debts, the face in the right databases — an identity dismantled piece by piece until there is nothing left to recognize.' },
      { label: 'Relocate to safer ground', mag: 0.52, when: A(fameGte('renowned'), resGte('wealthy')),
        does: 'activity → "relocating to safer ground"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'relocating to safer ground' },
        stub: '{actor} accepts that a recognizable face cannot outlast the neighborhood that recognizes it, and pays for the quiet logistics of being somewhere else entirely before anyone thinks to look.' },
      { label: 'Change the face they show the street', mag: 0.44, when: A(fameGte('known'), resGte('comfortable')),
        does: 'activity → "altering their appearance"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'altering their appearance' },
        stub: '{actor} is recognizable enough that habit alone will not protect them, so they spend on the cosmetic arithmetic of not being noticed: hair, clothes, gait, the small paid alterations that make a familiar face unfamiliar.' },
      { label: 'Harden or sanitize a safehouse', mag: 0.4, when: A(place('actor', 'haven'), O(outPair('actor', 'contact:lodging'), anyCur('actor', ['fixer', 'route_familiar', 'safehouse_operator', 'survivalist']))),
        does: 'activity → "hardening a safehouse"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'hardening a safehouse' },
        stub: '{actor} spends the turn making the safe place safer: cleaning traces, changing habits, checking exits, and removing the small comforts that become evidence.' },
      { label: 'Go dark and reduce signal exposure', mag: 0.36, when: O(outPair('actor', 'contact:social'), anyCur('actor', ['ghostprint_active', 'hacker', 'off_grid', 'paranoid', 'signal_operator'])),
        does: 'activity → "reducing signal exposure"', event: 'signal_exposure_reduced',
        delta: { 'character.current_activity': 'reducing signal exposure' },
        stub: '{actor} trims their signal down to almost nothing — no unnecessary pings, no sentimental check-ins, no pattern that would let a watcher say yes, there.' },
      { label: 'Run a counter-surveillance sweep', mag: 0.34, when: O(anyCur('actor', ['combat_trained', 'hacker', 'informant_handler', 'paranoid', 'scout', 'surveillance_capable']), evRecent('compliance_alert', 'actor', 8)),
        does: 'activity → "running counter-surveillance"', event: 'counter_surveillance_sweep',
        delta: { 'character.current_activity': 'running counter-surveillance' },
        stub: '{actor} checks whether anyone has learned the shape of their absence: doubled-back routes, watcher positions, unusual queries, and the tiny repetitions that turn hiding into a map.' },
      { label: 'Shift a mobile route without surfacing', mag: 0.3, when: A(O(inTransit(), hasDest()), anyCur('actor', ['fugitive', 'route_familiar', 'travel_ready', 'wanted'])),
        does: 'activity → "shifting concealed route"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'shifting concealed route' },
        stub: '{actor} changes the route without making the change look like a change, letting timing and terrain do what panic would ruin.' },
      { label: 'Preserve the silence another day', mag: 0.22, when: ALWAYS,
        does: 'activity → "preserving concealment"', event: 'hideout_maintained',
        delta: { 'character.current_activity': 'preserving concealment' },
        stub: '{actor} does the unglamorous work of staying missing: small routines, smaller footprints, and the discipline not to reach toward the people who would make the silence easier to bear.' },
    ],
  },
  {
    id: 'HONOR_DEBT', tid: 'honor_debt', band: 'project', priority: 80, slots: ['ACTOR'], ptp: false,
    bandNote: 'Honor/debt pressure is a story obligation that may preempt ordinary maintenance when the relevant ledger is hot.',
    blurb: 'A binding obligation surfaces from the blank years.',
    gate: O(eph('actor', 'debt_pulse_active'), evRecent('encoded_message', 'actor', 3)),
    branches: [
      { label: 'Activate the Ghostprint Key at a sympathetic node', mag: 0.66, when: A(tag('actor', 'ghostprint_active'), A(place('actor', 'subterranean'), place('actor', 'transit'))),
        does: 'activity → "signaling through a sympathetic node"', event: 'honor_debt',
        delta: { 'character.current_activity': 'signaling through a sympathetic node' },
        stub: '{actor} finds a half-decommissioned authentication terminal and pulses the Key against it.' },
      { label: 'Fulfill obligation through a dead-drop', mag: 0.5, when: outPair('actor', 'contact:social'),
        does: 'activity → "servicing an old debt"', event: 'honor_debt',
        delta: { 'character.current_activity': 'servicing an old debt' },
        stub: '{actor} tucks an encoded microdrive behind a loose ceramic tile and leaves a mark for the recipient.' },
      { label: 'Leave a public sign', mag: 0.38, when: ALWAYS,
        does: 'activity → "leaving a coded public sign"', event: 'honor_debt',
        delta: { 'character.current_activity': 'leaving a coded public sign' },
        stub: '{actor} pays a street artist in physical cash to place a specific glyph where only the intended recipient will read it.' },
    ],
  },
  {
    id: 'WARN_ALLY', tid: 'warn_ally', band: 'crisis', priority: 75, slots: ['ACTOR', 'TARGET'], ptp: true,
    blurb: 'A threat surfaces; word reaches the people who need to know.',
    gate: A(
      O(relShared('family'), relShared('romantic'), relShared('chosen_kin'), relShared('comrade'), relShared('ally')),
      O(evRecent('threat_issued', 'target', 3), evRecent('compliance_alert', 'target', 3), inPair('target', 'hunting')),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Reach the ally face-to-face before the word gets out', mag: 0.66, when: A(colo(), N(dramatic())),
        does: 'activity → "delivering urgent warning in person"; adds `forewarned` to target', event: 'warning_delivered',
        delta: { 'character.current_activity': 'delivering urgent warning in person', 'entity_tags.add': ['forewarned → target'] },
        stub: '{actor} catches {target} before they have time to compose themselves and tells them quickly, in a voice stripped to the load-bearing words, what is coming and what they should do about it.',
        pressure: '{actor} is moving to deliver an urgent warning to {target}. The scene may show this as interruption, intrusion, or a beat the storyteller folds into the current moment.' },
      { label: 'Send word through whatever channel will reach them quickest', mag: 0.52, when: N(dramatic()),
        does: 'activity → "sending urgent warning"; adds `forewarned` to target', event: 'warning_delivered',
        delta: { 'character.current_activity': 'sending urgent warning', 'entity_tags.add': ['forewarned → target'] },
        stub: '{actor} sends the warning through whatever channel will reach {target} fastest — a call, a runner, a sealed message, a coded signal — and hopes the gap between sending and receiving is short enough to matter.',
        pressure: '{actor} has sent {target} an urgent warning by remote means. The scene may show this as an incoming message, a vague disturbance, a half-heard signal, or it may not land in time.' },
      { label: 'Leak the warning without breaking cover', mag: 0.4, when: ALWAYS,
        does: 'activity → "leaking urgent warning"; adds `forewarned` to target', event: 'warning_delivered',
        delta: { 'character.current_activity': 'leaking urgent warning', 'entity_tags.add': ['forewarned → target'] },
        stub: '{actor} still sends the warning, but strips their own hand from it: a proxy, a coded leak, an anonymous ping, something that can reach {target} without making contact itself the story.',
        pressure: '{actor} has sent {target} an indirect warning. It may appear as a leak, proxy message, coded signal, or not land in time; Orrery is not deciding how {target} responds.' },
    ],
  },
  {
    id: 'PURSUE_GHOST_LEAD', tid: 'pursue_ghost_lead', band: 'project', priority: 60, slots: ['ACTOR'], ptp: false,
    bandNote: 'Ghost-lead pursuit is a long-arc motive with explicit clue pressure, so it can outrank routine maintenance.',
    blurb: 'The fragments of a buried identity tug at the actor.',
    gate: A(tag('actor', 'seeking_identity'), tod(['evening', 'night']), N(inPair('actor', 'hunting'))),
    branches: [
      { label: 'Recon a hideout their body remembers', mag: 0.64, when: A(place('actor', 'subterranean'), place('actor', 'transit')),
        does: 'activity → "reconning remembered terrain"', event: 'pursue_identity_lead',
        delta: { 'character.current_activity': 'reconning remembered terrain' },
        stub: '{actor} picks through maintenance corridors to a place their body recognizes before memory can explain why.' },
      { label: 'Probe the data fog with the Key', mag: 0.57, when: tag('actor', 'ghostprint_active'),
        does: 'activity → "probing identity records"', event: 'pursue_identity_lead',
        delta: { 'character.current_activity': 'probing identity records' },
        stub: '{actor} brushes against a mid-tier operator, ducks into a kiosk, and lets the Key scrape fragments from the ledger noise.' },
      { label: 'Query the broker network', mag: 0.44, when: ALWAYS,
        does: 'activity → "querying the broker network"', event: 'pursue_identity_lead',
        delta: { 'character.current_activity': 'querying the broker network' },
        stub: '{actor} visits a broker who owes them a favor and leaves with one new question and one dangerous name.' },
    ],
  },
  {
    id: 'CHECK_ON_DEPENDENT', tid: 'check_on_dependent', band: 'affil', priority: 55, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Dependent care is affiliation with responsibility attached, so it can preempt ordinary maintenance.',
    blurb: 'A duty of care surfaces between the actor and someone in their charge.',
    gate: A(
      N(tag('actor', 'informant_handler')),
      O(relDir('handler'), relDir('mentor'), relDir('patron'), relDir('guardian')),
      cooldown('contact_made', 'pair', 12),
      cooldown('welfare_check', 'pair', 12),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'grudge_active')),
    ),
    branches: [
      { label: 'Drop by in person when the moment allows', mag: 0.44, when: A(colo(), cooldown('welfare_check', 'pair', 6)),
        does: 'activity → "checking on a dependent in person"', event: 'welfare_check',
        delta: { 'character.current_activity': 'checking on a dependent in person' },
        stub: '{actor} stops by — ostensibly for something else, the way these visits often are — and uses the small window to read {target}\u2019s state: how they look, what they say without saying, what they decline to mention.',
        pressure: '{actor} is making a casual welfare check on {target}. Treat as a low-key social presence the scene can absorb or use as a beat of relationship texture.' },
      { label: 'Reach out through customary channels', mag: 0.22, when: ALWAYS,
        does: 'activity → "checking in on a dependent"', event: 'contact_made',
        delta: { 'character.current_activity': 'checking in on a dependent' },
        stub: '{actor} sends the kind of message they always send — brief, light in tone, asking nothing real but leaving the door open for {target} to say something real if they want to — and watches for what comes back.',
        pressure: '{actor} has sent {target} a routine welfare-check message. The scene may use this as an unread notification, an answered exchange, or texture for {target}\u2019s decisions.' },
    ],
  },
  {
    id: 'CULTIVATE_INFORMANT', tid: 'cultivate_informant', band: 'project', priority: 50, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Informant cultivation is relationship-shaped, but it serves an active project rather than ordinary affiliation.',
    blurb: 'Patient intelligence work with a specific asset.',
    gate: A(
      tag('actor', 'informant_handler'),
      O(relDir('handler'), L('relDirRev', { t: 'asset' }, 'target has `asset` relationship to actor')),
      cooldown('informant_contact', 'pair', 4),
      cooldown('intel_acquired', 'pair', 4),
      tod(['evening', 'night']),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'grudge_active')),
    ),
    branches: [
      { label: 'Press for material intel when trust is sufficient', mag: 0.62, when: A(colo(), trustGte(2), cooldown('intel_acquired', 'pair', 6)),
        does: 'activity → "acquiring material intelligence"; adds `intelligence_asset_active` to actor', event: 'intel_acquired',
        delta: { 'character.current_activity': 'acquiring material intelligence', 'entity_tags.add': ['intelligence_asset_active'] },
        stub: '{actor} meets {target} in a place that looks ordinary to anyone watching and asks the question they\u2019ve been working toward for weeks. {target} doesn\u2019t answer immediately. Then they do.',
        pressure: '{actor} may be trying to extract material intel from {target} while {target} is in the current scene. Use it only if it creates a believable opening, signal, or complication.' },
      { label: 'Routine contact to maintain the relationship', mag: 0.28, when: A(colo(), trustGte(0)),
        does: 'activity → "maintaining informant contact"', event: 'informant_contact',
        delta: { 'character.current_activity': 'maintaining informant contact' },
        stub: '{actor} sees {target} in passing — a transactional exchange with nothing to it, except that the exchange itself is the point. The relationship needs maintenance whether or not there is anything to report.',
        pressure: '{actor} is maintaining contact with {target} through a subtle off-screen channel. It can surface as a message, glance, coded exchange, or be deferred.' },
      { label: 'Place a small overture from a distance', mag: 0.18, when: ALWAYS,
        does: 'activity → "courting an informant remotely"', event: 'informant_contact',
        delta: { 'character.current_activity': 'courting an informant remotely' },
        stub: '{actor} routes a small gift or unexpected courtesy to {target} through indirect channels — the kind of gesture that lands without obligation but accumulates over time into something the asset will eventually want to repay.',
        pressure: '{actor} has placed a small indirect overture for {target}. Treat it as optional atmosphere or a hook the Storyteller can choose to pick up.' },
    ],
  },
  {
    id: 'KEEP_VIGIL', tid: 'keep_vigil', band: 'affil', priority: 50, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Vigil is affiliation under acute pressure, so it can outrank ordinary maintenance while a target is wounded or dying.',
    blurb: 'The actor remains present through a slow, uncertain hour.',
    gate: A(
      colo(),
      O(eph('target', 'wounded'), eph('target', 'dying'), eph('target', 'unconscious'), eph('target', 'captive')),
      O(relDir('family'), relDir('romantic'), relDir('chosen_kin'), relDir('comrade'), relDir('ward'), relDir('guardian'), relDir('captor')),
      cooldown('vigil_held', 'actor', 2),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Maintain prayerful or meditative presence', mag: 0.46, when: anyTag('actor', ['devout', 'contemplative', 'ritual_practitioner']),
        does: 'activity → "holding meditative vigil"; adds `at_vigil` to actor', event: 'vigil_held',
        delta: { 'character.current_activity': 'holding meditative vigil', 'entity_tags.add': ['at_vigil'] },
        stub: '{actor} sits beside {target} with hands quiet, breathing matched to whatever rhythm {target}\u2019s body is still finding.',
        pressure: '{actor} is keeping a contemplative vigil over {target}. Use this as an emotional anchor in the scene, not an active intervention.' },
      { label: 'Speak softly through the long hours', mag: 0.38, when: eph('target', 'unconscious'),
        does: 'activity → "speaking through the long hours"; adds `at_vigil` to actor', event: 'vigil_held',
        delta: { 'character.current_activity': 'speaking through the long hours', 'entity_tags.add': ['at_vigil'] },
        stub: '{actor} tells {target} small things — what the light is doing outside, what the others said today — in the belief that whatever can be reached should be reached.',
        pressure: '{actor} is speaking to an unresponsive {target} through a long stretch. Treat as audible presence the scene can thread through quieter moments.' },
      { label: 'Stand watch with attention but without intervention', mag: 0.32, when: ALWAYS,
        does: 'activity → "standing vigil"; adds `at_vigil` to actor', event: 'vigil_held',
        delta: { 'character.current_activity': 'standing vigil', 'entity_tags.add': ['at_vigil'] },
        stub: '{actor} stays. Not doing anything — that\u2019s the point of being here. {target} is alone with whatever is happening to them, and {actor} is the witness who makes that aloneness less complete.',
        pressure: '{actor} is keeping silent vigil over {target}. Use this as ambient presence — a witness who shapes the scene by being there, not by acting.' },
    ],
  },
  {
    id: 'SURVEIL', tid: 'surveil', band: 'project', priority: 48, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Surveillance usually serves live threat or investigation arcs, so it can sit above routine and social maintenance.',
    blurb: 'Watching from afar without turning observation into contact.',
    gate: A(
      hydrated(),
      N(constrained()),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'grudge_active')),
      O(hiddenOff(), outPair('actor', 'contact:social'), anyCur('actor', ['broker', 'hacker', 'informant_handler', 'intelligence_asset_active', 'paranoid', 'researcher', 'signal_operator', 'surveillance_capable']), relDir('captor'), relDir('guardian'), relDir('handler'), trustLt(-2), evRecent('threat_issued', 'target', 8)),
      cooldown('surveillance_performed', 'pair', 6),
      cooldown('intel_reviewed', 'pair', 6),
    ),
    branches: [
      { label: 'Intercept signal traffic', mag: 0.48, when: anyCur('actor', ['ghostprint_active', 'hacker', 'researcher', 'signal_operator', 'surveillance_capable']),
        does: 'activity → "intercepting target signals"', event: 'surveillance_performed',
        delta: { 'character.current_activity': 'intercepting target signals' },
        stub: '{actor} watches the signal field around {target}: not the person directly, not yet, but the traffic and absences that make a life legible to someone patient enough.',
        pressure: '{actor} may be reading signal traffic around {target}\u2019s current scene. Use it as optional pressure or atmosphere, not as a canonical breach unless the scene earns it.' },
      { label: 'Keep tabs from a distance', mag: 0.44, when: O(hiddenOff(), trustLt(-2)),
        does: 'activity → "keeping tabs from a distance"', event: 'surveillance_performed',
        delta: { 'character.current_activity': 'keeping tabs from a distance' },
        stub: '{actor} keeps tabs on {target} without touching the line between them: a pattern noticed, a channel checked, a small confirmation that does not become contact.',
        pressure: '{actor} is keeping tabs on {target} from off-screen. Treat this as possible pressure, unease, traces, or delayed setup; do not turn it into automatic contact or control of {target}\u2019s choices.' },
      { label: 'Collect a proxy watcher report', mag: 0.38, when: O(outPair('actor', 'contact:social'), anyCur('actor', ['broker', 'fixer', 'informant_handler'])),
        does: 'activity → "collecting a proxy watcher report"', event: 'surveillance_performed',
        delta: { 'character.current_activity': 'collecting a proxy watcher report' },
        stub: '{actor} does not go near {target}. They let someone else look, then read the report for what the watcher understood and what they were too ordinary to notice.',
        pressure: '{actor} has someone off-screen watching for signs around {target}. This can surface as a watcher, rumor, false alarm, or nothing at all.' },
      { label: 'Review accumulated intel', mag: 0.34, when: anyCur('actor', ['academic', 'intelligence_asset_active', 'paranoid', 'researcher']),
        does: 'activity → "reviewing accumulated intel"', event: 'intel_reviewed',
        delta: { 'character.current_activity': 'reviewing accumulated intel' },
        stub: '{actor} stops gathering and starts reading: old logs, half-useful reports, fragments whose meaning only appears after the same question has been asked too many times.',
        pressure: '{actor} is reviewing accumulated intel related to {target}. If useful, let the scene feel watched or anticipated; the review itself does not force new facts into canon.' },
      { label: 'Follow the public pattern', mag: 0.3, when: pubFlow('target'),
        does: 'activity → "following target public pattern"', event: 'surveillance_performed',
        delta: { 'character.current_activity': 'following target public pattern' },
        stub: '{actor} follows the public shape of {target}\u2019s life: where they appear, what routes repeat, which absences look chosen and which look imposed.',
        pressure: '{actor} may have mapped the public pattern around {target}. Use this only as Storyteller-controlled scene pressure or a future setup.' },
      { label: 'Keep the target in view without contact', mag: 0.24, when: ALWAYS,
        does: 'activity → "surveilling without contact"', event: 'surveillance_performed',
        delta: { 'character.current_activity': 'surveilling without contact' },
        stub: '{actor} keeps {target} in view at the lowest useful resolution, choosing continued uncertainty over the kind of move that would make the watching visible.',
        pressure: '{actor} is watching around {target} but has not made contact. The Storyteller may adapt, delay, ignore, or incorporate that pressure without letting Orrery decide what {target} does.' },
    ],
  },
  {
    id: 'REACH_OUT_TO_KIN', tid: 'reach_out_to_kin', band: 'affil', priority: 40, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Kin maintenance is allowed to beat everyday self-maintenance when the relationship has gone quiet long enough.',
    blurb: 'A small thread of contact between people who hold each other.',
    gate: A(
      O(relShared('family'), relShared('romantic'), relShared('chosen_kin'), relShared('comrade')),
      O(mutualWarm(), trustLoaded(), dramatic()),
      cooldown('contact_made', 'pair', 8),
      cooldown('kin_visit', 'pair', 8),
      cooldown('contact_deferred', 'pair', 8),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'grudge_active')),
    ),
    branches: [
      { label: 'Find the moment for a real face-to-face conversation', mag: 0.36, when: A(colo(), mutualWarm(), N(dramatic()), cooldown('kin_visit', 'pair', 5)),
        does: 'activity → "spending real time with kin"', event: 'kin_visit',
        delta: { 'character.current_activity': 'spending real time with kin' },
        stub: '{actor} makes the small effort that finding-time-for-someone requires — clearing a half hour, choosing a place, showing up — and {target} arrives, and for a while they are the kind of present together that distance erodes.',
        pressure: '{actor} is meeting {target} in person for a real conversation. Use this as a relationship beat the scene can fold in or hold for later, not as a guaranteed off-screen event.' },
      { label: 'Send a message that says less than it means', mag: 0.16, when: A(mutualWarm(), N(dramatic())),
        does: 'activity → "keeping kin contact warm"', event: 'contact_made',
        delta: { 'character.current_activity': 'keeping kin contact warm' },
        stub: '{actor} sends {target} the small message that means more than the words it contains — a check-in, a shared joke, a question that doesn\u2019t really need answering — and the thread between them stays warm for another while.',
        pressure: '{actor} has sent {target} a small affectionate message. Treat as ambient relationship-warmth — possibly an incoming notification, possibly not surfaced at all.' },
      { label: 'Draft the message and leave it unsent', mag: 0.18, when: O(trustLoaded(), dramatic()),
        does: 'activity → "drafting unsent kin contact"', event: 'contact_deferred',
        delta: { 'character.current_activity': 'drafting unsent kin contact' },
        stub: '{actor} writes the message anyway, or composes the call in their head, and then does not send it. The wanting is real; so is the cost of turning it into contact.',
        pressure: '{actor} is holding back a loaded attempt to reach {target}. Use this as optional emotional pressure or a future story beat; Orrery has not made contact happen.' },
      { label: 'Let the silence stand for now', mag: 0.08, when: ALWAYS,
        does: 'activity → "deferring kin contact"', event: 'contact_deferred',
        delta: { 'character.current_activity': 'deferring kin contact' },
        stub: '{actor} lets the thread remain unpulled. Whatever exists between them and {target}, it is not made warmer by forcing the wrong kind of contact today.',
        pressure: '{actor} is choosing not to contact {target} for now. Treat this as optional subtext, not as a visible scene event.' },
    ],
  },
  {
    id: 'CONSULT_RIVAL', tid: 'consult_rival', band: 'project', priority: 35, slots: ['ACTOR', 'TARGET'], ptp: true,
    bandNote: 'Rival consultation is a deliberate project move, not casual social contact, and can outrank routine obligations.',
    blurb: 'Two people who do not trust each other are forced into contact anyway.',
    gate: A(
      O(relDir('rival'), trustLt(0)),
      O(evRecent('compliance_alert', 'any', 10), evRecent('threat_issued', 'any', 10), evRecent('faction_realignment', 'any', 15)),
      cooldown('contact_made', 'pair', 20),
      cooldown('rival_consulted', 'pair', 20),
      N(eph('actor', 'grudge_active')),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Meet face-to-face on neutral ground', mag: 0.62, when: A(colo(), O(place('actor', 'meeting'), place('actor', 'commerce'), place('actor', 'place_open'))),
        does: 'activity → "meeting a rival under truce"; adds `under_truce` to both', event: 'rival_consulted',
        delta: { 'character.current_activity': 'meeting a rival under truce', 'entity_tags.add': ['under_truce', 'under_truce → target'] },
        stub: '{actor} and {target} arrange to be in the same place at the same time without quite arranging it — both of them drinking something they don\u2019t particularly want, both of them speaking carefully — because whatever is happening is bigger than what they have between them, and they both know it.',
        pressure: '{actor} is in a tense face-to-face meeting with {target}, a known rival. Treat as charged co-presence — the scene can show this as observed truce, ambient discomfort, or delayed consequence.' },
      { label: 'Send a carefully-worded message through indirect channels', mag: 0.48, when: outPair('actor', 'contact:social'),
        does: 'activity → "reaching out to a rival via intermediary"', event: 'rival_consulted',
        delta: { 'character.current_activity': 'reaching out to a rival via intermediary' },
        stub: '{actor} sends {target} a message routed through an intermediary they both trust slightly more than they trust each other — worded with enough care that the relay can be denied later, but with enough substance that {target} cannot reasonably ignore it.',
        pressure: '{actor} has sent {target} a carefully-routed message via intermediary. Treat as off-screen pressure — the scene may show {target} reacting to it, or it may resurface later.' },
      { label: 'Leave a sign the rival will recognize and a door they can open', mag: 0.34, when: ALWAYS,
        does: 'activity → "leaving a tentative overture for a rival"', event: 'contact_made',
        delta: { 'character.current_activity': 'leaving a tentative overture for a rival' },
        stub: '{actor} doesn\u2019t quite reach out — but they place a sign where {target} will see it, the kind of signal that says *I am willing to talk if you are*, without committing to anything.',
        pressure: '{actor} has placed a discreet overture for {target} to find. Treat as a passive hook the scene can pick up if useful, or leave dormant.' },
    ],
  },
  {
    id: 'ROUTINE_COMMUTE', tid: 'routine_commute', band: 'routine', priority: 26, slots: ['ACTOR'], ptp: false,
    bandNote: 'Commute resolves where a routine-bound actor should be before nearby maintenance packages pick a place-shaped branch.',
    blurb: 'Ordinary home/work movement from explicit routine anchors.',
    gate: A(
      hydrated(),
      N(constrained()),
      N(inTransit()),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'wounded')),
      N(eph('actor', 'grieving')),
      O(A(anchorHas('work'), anchorDue('work'), anchorAway('work')), A(anchorHas('home'), anchorDue('home'), anchorAway('home'))),
    ),
    branches: [
      { label: 'Commute to the scheduled workplace', mag: 0.16, when: A(anchorHas('work'), anchorDue('work'), anchorAway('work'), anchorResolves('work')),
        does: 'activity → "commuting to work"; starts planned travel', event: 'travel_departed',
        delta: { 'character.current_activity': 'commuting to work', 'travel.start': 'work anchor' },
        stub: '{actor} follows the ordinary route toward work: not a quest, not a crisis, just the daily movement that keeps a normal life legible.' },
      { label: 'Commute home after the day\u2019s obligations', mag: 0.14, when: A(anchorHas('home'), anchorDue('home'), anchorAway('home'), anchorResolves('home')),
        does: 'activity → "commuting home"; starts planned travel', event: 'travel_departed',
        delta: { 'character.current_activity': 'commuting home', 'travel.start': 'home anchor' },
        stub: '{actor} turns toward home with the unremarkable certainty of someone whose day has a next place.' },
      { label: 'Recheck routine before moving', mag: 0.04, when: ALWAYS,
        does: 'activity → "checking routine timing"', event: 'travel_prepared',
        delta: { 'character.current_activity': 'checking routine timing' },
        stub: '{actor} pauses at the edge of routine and checks the ordinary facts before moving: where they are, where the day says they should be, and whether the next leg is real.' },
    ],
  },
  {
    id: 'MOURN_LOSS', tid: 'mourn_loss', band: 'affil', priority: 25, slots: ['ACTOR'], ptp: false,
    bandNote: 'Fresh grief suppresses ordinary social, intimacy, and routine loops; it should beat low-grade bodily maintenance.',
    blurb: 'A loss settles into the body across many quiet days.',
    gate: A(eph('actor', 'grieving'), cooldown('mourning_act', 'actor', 3), N(inPair('actor', 'hunting'))),
    branches: [
      { label: 'Visit the place of remembrance', mag: 0.42, when: O(place('actor', 'tomb'), place('actor', 'sacred')),
        does: 'activity → "tending the dead"', event: 'mourning_act',
        delta: { 'character.current_activity': 'tending the dead' },
        stub: '{actor} returns to the place where the dead are kept — stone, name, photograph, marker, whatever this world has made for the purpose — and stands long enough to be still and remember, before going back to the work of being alive.' },
      { label: 'Sit with others who carry the same loss', mag: 0.38, when: othersGrieving(),
        does: 'activity → "gathering with co-mourners"', event: 'mourning_act',
        delta: { 'character.current_activity': 'gathering with co-mourners' },
        stub: '{actor} finds the others who knew the dead and sits with them — wordlessly, mostly.' },
      { label: 'Pour the loss into the day\u2019s work', mag: 0.28, when: anyTag('actor', ['musician', 'writer', 'artisan', 'scholar', 'arcane_caster', 'soldier', 'keeps_shop', 'domestic_role']),
        does: 'activity → "working through grief"', event: 'mourning_act',
        delta: { 'character.current_activity': 'working through grief' },
        stub: '{actor} returns to their work — the thing the loss hasn\u2019t taken — and does it with the dead person sitting somewhere just behind them, watching the work with the particular silence the dead have.' },
      { label: 'Carry the weight in private', mag: 0.14, when: ALWAYS,
        does: 'activity → "carrying private grief"', event: 'mourning_act',
        delta: { 'character.current_activity': 'carrying private grief' },
        stub: '{actor} goes through the day\u2019s motions with the loss settled inside them like a second heartbeat — not louder than the day, just underneath it.' },
    ],
  },
  {
    id: 'SLEEP', tid: 'sleep', band: 'embodied', priority: 25, slots: ['ACTOR'], ptp: false,
    blurb: 'The body asks for the thing without which it cannot continue.',
    gate: A(
      O(A(tod(['night']), need('sleep', 8)), need('sleep', 16)),
      N(eph('actor', 'cns_stimulated')),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Collapse into deferred sleep', mag: 0.74, when: need('sleep', 48),
        does: 'activity → "collapsing into deferred sleep"; fulfills `sleep`, quality `collapse_rough`, discharge 4', event: 'slept',
        delta: { 'character.current_activity': 'collapsing into deferred sleep', 'need.fulfill': 'sleep · collapse_rough · discharge 4' },
        stub: '{actor} stops negotiating with exhaustion. Whatever place they have reached becomes the place where the body claims its overdue sleep.' },
      { label: 'Sleep at home', mag: 0.22, when: A(place('actor', 'dwelling'), residesHere()),
        does: 'activity → "sleeping at home"; fulfills `sleep`, quality `good`, discharge 10', event: 'slept',
        delta: { 'character.current_activity': 'sleeping at home', 'need.fulfill': 'sleep · good · discharge 10' },
        stub: '{actor} reaches familiar shelter and lets sleep take them where the room already knows their shape.' },
      { label: 'Sleep in safe lodgings', mag: 0.28, when: O(O(place('actor', 'dwelling'), place('actor', 'haven')), outPair('actor', 'contact:lodging')),
        does: 'activity → "sleeping in safe lodgings"; fulfills `sleep`, quality `adequate`, discharge 7', event: 'slept',
        delta: { 'character.current_activity': 'sleeping in safe lodgings', 'need.fulfill': 'sleep · adequate · discharge 7' },
        stub: '{actor} finds a place secure enough to become temporary shelter and lets the unfamiliar room do enough of the work.' },
      { label: 'Sleep rough in cover or transit', mag: 0.36, when: ALWAYS,
        does: 'activity → "sleeping rough"; fulfills `sleep`, quality `rough`, discharge 3', event: 'slept',
        delta: { 'character.current_activity': 'sleeping rough', 'need.fulfill': 'sleep · rough · discharge 3' },
        stub: '{actor} sleeps in fragments, taking what rest the place allows and waking with some part of the debt still unpaid.' },
    ],
  },
  {
    id: 'DRINK', tid: 'drink', band: 'embodied', priority: 24, slots: ['ACTOR'], ptp: false,
    blurb: 'The body asks for water; what it accepts shapes the small hour.',
    gate: A(
      need('thirst', 2),
      O(need('thirst', 16), N(A(need('hunger', 4), tod(['morning', 'afternoon', 'evening']), O(A(place('actor', 'dwelling'), residesHere()), O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting'), place('actor', 'production')))))),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Drink desperately, whatever is available', mag: 0.56, when: need('thirst', 16),
        does: 'activity → "drinking to relieve severe thirst"; fulfills `thirst`, quality `desperate`', event: 'drank',
        delta: { 'character.current_activity': 'drinking to relieve severe thirst', 'need.fulfill': 'thirst · desperate' },
        stub: '{actor} drinks with the single-mindedness that severe thirst produces, past concern for source or dignity.' },
      { label: 'Drink in a public room', mag: 0.22, when: O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting')),
        does: 'activity → "drinking in company"; fulfills `thirst`, quality `social`', event: 'drank',
        delta: { 'character.current_activity': 'drinking in company', 'need.fulfill': 'thirst · social' },
        stub: '{actor} drinks what the room serves and lets the small ritual of holding a cup make the hour easier.' },
      { label: 'Drink from a public or wild source', mag: 0.14, when: O(place('actor', 'water_source'), place('actor', 'wilderness')),
        does: 'activity → "drinking from an available source"; fulfills `thirst`, quality `available_source`', event: 'drank',
        delta: { 'character.current_activity': 'drinking from an available source', 'need.fulfill': 'thirst · available_source' },
        stub: '{actor} drinks from whatever the place provides, and the relief of water makes the rest of the day briefly simpler.' },
      { label: 'Drink routinely from what is at hand', mag: 0.1, when: ALWAYS,
        does: 'activity → "drinking routinely"; fulfills `thirst`, quality `routine`', event: 'drank',
        delta: { 'character.current_activity': 'drinking routinely', 'need.fulfill': 'thirst · routine' },
        stub: '{actor} drinks because the body has been quietly asking, then returns to the shape of the hour.' },
    ],
  },
  {
    id: 'EAT', tid: 'eat', band: 'embodied', priority: 22, slots: ['ACTOR'], ptp: false,
    blurb: 'The body asks for fuel; what it gets matters more than the cookbook suggests.',
    gate: A(
      need('hunger', 4),
      O(tod(['morning', 'afternoon', 'evening']), need('hunger', 8)),
      N(inPair('actor', 'hunting')),
    ),
    branches: [
      { label: 'Eat ravenously, whatever is available', mag: 0.62, when: need('hunger', 16),
        does: 'activity → "eating to relieve severe hunger"; fulfills `hunger`, quality `desperate`', event: 'ate',
        delta: { 'character.current_activity': 'eating to relieve severe hunger', 'need.fulfill': 'hunger · desperate' },
        stub: '{actor} eats with the inattention of real hunger, relief overtaking any concern about what the food ought to be.' },
      { label: 'Eat at home with household', mag: 0.22, when: A(A(place('actor', 'dwelling'), residesHere()), anyTag('actor', ['married', 'parent', 'extended_household'])),
        does: 'activity → "sharing a household meal"; fulfills `hunger`, quality `household_meal`', event: 'ate',
        delta: { 'character.current_activity': 'sharing a household meal', 'need.fulfill': 'hunger · household_meal' },
        stub: '{actor} sits down to the meal that home means and lets being-with stand in for being-alone for a while.' },
      { label: 'Eat at home alone', mag: 0.2, when: A(place('actor', 'dwelling'), residesHere()),
        does: 'activity → "eating at home"; fulfills `hunger`, quality `home_meal`', event: 'ate',
        delta: { 'character.current_activity': 'eating at home', 'need.fulfill': 'hunger · home_meal' },
        stub: '{actor} makes the kind of meal home makes possible: unremarkable, private, and enough to let the evening continue on ordinary terms.' },
      { label: 'Eat in a public dining place', mag: 0.26, when: O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting'), place('actor', 'production')),
        does: 'activity → "eating in a public place"; fulfills `hunger`, quality `public_meal`', event: 'ate',
        delta: { 'character.current_activity': 'eating in a public place', 'need.fulfill': 'hunger · public_meal' },
        stub: '{actor} eats something the place can provide and watches the room continue its public life around them.' },
      { label: 'Forage or hunt from the country', mag: 0.38, when: A(place('actor', 'wilderness'), anyTag('actor', ['forager', 'hunter', 'survivalist', 'ranger', 'scout'])),
        does: 'activity → "foraging for a meal"; fulfills `hunger`, quality `wild_meal`', event: 'ate',
        delta: { 'character.current_activity': 'foraging for a meal', 'need.fulfill': 'hunger · wild_meal' },
        stub: '{actor} works the country for what the season has put within reach and makes a meal out of survival knowledge.' },
      { label: 'Eat from rations or what was packed', mag: 0.18, when: tag('actor', 'travel_provisioned'),
        does: 'activity → "eating travel rations"; fulfills `hunger`, quality `rations_meal`', event: 'ate',
        delta: { 'character.current_activity': 'eating travel rations', 'need.fulfill': 'hunger · rations_meal' },
        stub: '{actor} eats what was packed for exactly this kind of hour: practical, portable, and enough.' },
      { label: 'Find something and eat it', mag: 0.14, when: ALWAYS,
        does: 'activity → "eating opportunistically"; fulfills `hunger`, quality `opportunistic_meal`', event: 'ate',
        delta: { 'character.current_activity': 'eating opportunistically', 'need.fulfill': 'hunger · opportunistic_meal' },
        stub: '{actor} eats what is nearest and workable, attentive mostly to the fact that the body can stop asking for now.' },
    ],
  },
  {
    id: 'TRAVEL', tid: 'travel', band: 'routine', priority: 21, slots: ['ACTOR'], ptp: false,
    blurb: 'A character moves between meaningful places without pretending the road is a room.',
    gate: A(O(inTransit(), hasDest()), N(eph('actor', 'wounded')), N(eph('actor', 'grieving'))),
    branches: [
      { label: 'Arrive where people can be encountered', mag: 0.36, when: A(inTransit(), travProg(0.95), travPurpose('socialize')),
        does: 'activity → "arriving where people gather"; arrives at travel destination', event: 'travel_arrived',
        delta: { 'character.current_activity': 'arriving where people gather', 'travel.arrive': 'destination' },
        stub: '{actor} reaches the place they picked because other people would be there. The route ends, and the social possibility becomes immediate rather than theoretical.' },
      { label: 'Arrive at the planned destination', mag: 0.34, when: A(inTransit(), travProg(0.95)),
        does: 'activity → "arriving at destination"; arrives at travel destination', event: 'travel_arrived',
        delta: { 'character.current_activity': 'arriving at destination', 'travel.arrive': 'destination' },
        stub: '{actor} reaches the destination at last. The route drops away behind them into the ordinary unreliability of maps, and the place ahead becomes immediate.' },
      { label: 'Lose time to bad conditions or route friction', mag: 0.24, when: A(inTransit(), O(travRisk(['high', 'extreme']), weather(['rain', 'snow', 'fog']))),
        does: 'activity → "delayed in transit"; records travel delay', event: 'travel_delayed',
        delta: { 'character.current_activity': 'delayed in transit', 'travel.delay': 'recorded' },
        stub: '{actor} loses time to the route itself — weather, traffic, closed access, or the thousand small refusals a city can make when someone is trying to cross it.' },
      { label: 'Make steady progress along the route', mag: 0.18, when: inTransit(),
        does: 'activity → "traveling toward destination"; advances travel by 0.35', event: 'travel_progressed',
        delta: { 'character.current_activity': 'traveling toward destination', 'travel.advance': '0.35' },
        stub: '{actor} keeps moving: transfers, crossings, service corridors, streets whose names matter less than the fact that each one puts the destination a little closer.' },
      { label: 'Charter private transport', mag: 0.3, when: A(hasDest(), N(inTransit()), resGte('wealthy')),
        does: 'activity → "departing by chartered transport"; starts planned travel', event: 'travel_departed',
        delta: { 'character.current_activity': 'departing by chartered transport', 'travel.start': 'planned' },
        stub: '{actor} does not queue, transfer, or wait. Money turns the journey into a closed door and a window: a private vehicle, a paid schedule, a route that exists because they asked for it.' },
      { label: 'Slip out along covert routes', mag: 0.32, when: A(hasDest(), N(inTransit()), fameGte('renowned'), O(tag('actor', 'travel_ready'), tag('actor', 'travel_provisioned'), tag('actor', 'route_familiar'))),
        does: 'activity → "departing along covert routes"; starts planned travel', event: 'travel_departed',
        delta: { 'character.current_activity': 'departing along covert routes', 'travel.start': 'planned' },
        stub: '{actor} cannot ride public flow without being a sighting, so the route runs through the city\u2019s blind spots: service levels, freight corridors, the hours and angles where a recognizable face passes unwitnessed.' },
      { label: 'Depart toward the planned destination', mag: 0.28, when: A(hasDest(), N(inTransit()), O(tag('actor', 'travel_ready'), tag('actor', 'travel_provisioned'), tag('actor', 'route_familiar'), place('actor', 'transit'))),
        does: 'activity → "departing toward destination"; starts planned travel', event: 'travel_departed',
        delta: { 'character.current_activity': 'departing toward destination', 'travel.start': 'planned' },
        stub: '{actor} starts the journey with enough of a route in mind to make the first leg real. The exact path can change; the destination no longer can.' },
      { label: 'Prepare the journey rather than starting badly', mag: 0.12, when: ALWAYS,
        does: 'activity → "preparing route and supplies"; adds `travel_ready` to actor', event: 'travel_prepared',
        delta: { 'character.current_activity': 'preparing route and supplies', 'entity_tags.add': ['travel_ready'] },
        stub: '{actor} does not start badly. They check timing, supplies, weather, access, and the parts of the route that might betray them before they have earned the right to improvise.' },
    ],
  },
  {
    id: 'SOCIALIZE', tid: 'socialize', band: 'affil', priority: 18, slots: ['ACTOR'], ptp: false,
    bandNote: 'Accumulated social debt is allowed to interrupt generic work/routine before it becomes a crisis.',
    blurb: 'The need for the company of others, on whatever terms a character can have it.',
    gate: A(
      need('socialize', 24),
      cooldown('socialized', 'actor', 4),
      cooldown('socialized_alone', 'actor', 4),
      cooldown('social_travel_departed', 'actor', 4),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'grieving')),
      N(eph('actor', 'wounded')),
    ),
    branches: [
      { label: 'Host chosen company on their own ground', mag: 0.24, when: A(fameGte('renowned'), outPair('actor', 'contact:social')),
        does: 'activity → "hosting chosen company privately"; fulfills `socialize`, quality `private_company`', event: 'socialized',
        delta: { 'character.current_activity': 'hosting chosen company privately', 'need.fulfill': 'socialize · private_company' },
        stub: '{actor} does not go looking for company in rooms that would turn to watch them enter. They summon it instead: a few chosen people, a door that closes, an evening where nobody performs recognition.' },
      { label: 'Seek company after extended isolation', mag: 0.54, when: A(need('socialize', 168), N(othersColo(1)), N(O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting'), place('actor', 'place_open'))), pubFlow(), fameLt('renowned'), resolveDest(['commerce', 'entertainment', 'meeting', 'place_open'])),
        does: 'activity → "seeking company after isolation"; starts social travel', event: 'social_travel_departed',
        delta: { 'character.current_activity': 'seeking company after isolation', 'travel.start': 'social destination' },
        stub: '{actor} feels the particular pressure that comes from going too long without other people in their life, and moves toward somewhere there will be voices, even if those voices are not for them.' },
      { label: 'Engage with company already present', mag: 0.22, when: othersColo(1),
        does: 'activity → "engaging with present company"; fulfills `socialize`, quality `present_company`', event: 'socialized',
        delta: { 'character.current_activity': 'engaging with present company', 'need.fulfill': 'socialize · present_company' },
        stub: '{actor} spends real attention on the people around them — not transactional attention, the other kind — for long enough that the social need is briefly met without anyone naming it as such.' },
      { label: 'Seek a trusted voice rather than a crowd', mag: 0.22, when: A(anyTag('actor', ['solitary', 'reserved']), outPair('actor', 'contact:social')),
        does: 'activity → "talking with a trusted contact"; fulfills `socialize`, quality `trusted_contact`, discharge 72', event: 'socialized',
        delta: { 'character.current_activity': 'talking with a trusted contact', 'need.fulfill': 'socialize · trusted_contact · 72' },
        stub: '{actor} weighs the noise of a public room against the particular relief of one familiar voice, and chooses the voice — a long, unhurried exchange with someone who does not need anything explained.' },
      { label: 'Set out toward public company', mag: 0.26, when: A(N(othersColo(1)), N(O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting'), place('actor', 'place_open'))), pubFlow(), fameLt('renowned'), resolveDest(['commerce', 'entertainment', 'meeting', 'place_open'])),
        does: 'activity → "seeking public company"; starts social travel', event: 'social_travel_departed',
        delta: { 'character.current_activity': 'seeking public company', 'travel.start': 'social destination' },
        stub: '{actor} chooses movement over more empty time and sets out toward a place where other people can be encountered without requiring the story to pre-name them.' },
      { label: 'Go where people are', mag: 0.2, when: A(O(place('actor', 'commerce'), place('actor', 'entertainment'), place('actor', 'meeting'), place('actor', 'place_open')), fameLt('renowned')),
        does: 'activity → "passing time in a populated place"; fulfills `socialize`, quality `public_company`', event: 'socialized',
        delta: { 'character.current_activity': 'passing time in a populated place', 'need.fulfill': 'socialize · public_company' },
        stub: '{actor} goes to one of the places built around the fact that people gather there, and stays long enough to become part of the room\u2019s ordinary texture.' },
      { label: 'Reach out to a contact for no urgent reason', mag: 0.24, when: outPair('actor', 'contact:social'),
        does: 'activity → "reconnecting with a contact"; fulfills `socialize`, quality `remote_contact`, discharge 72', event: 'socialized',
        delta: { 'character.current_activity': 'reconnecting with a contact', 'need.fulfill': 'socialize · remote_contact · 72' },
        stub: '{actor} thinks of someone they have not spoken with in too long and reaches out for no urgent reason, which is its own kind of reason.' },
      { label: 'Practice parasocial company', mag: 0.16, when: ALWAYS,
        does: 'activity → "spending time with a stranger\u2019s voice"; fulfills `socialize`, quality `parasocial`, discharge 12', event: 'socialized_alone',
        delta: { 'character.current_activity': 'spending time with a stranger\u2019s voice', 'need.fulfill': 'socialize · parasocial · 12' },
        stub: '{actor} spends an hour with the voice of a stranger — a book, a serial, a recording — which is not the same as company but is enough like company to take the worst edge off.' },
    ],
  },
  {
    id: 'INTIMACY', tid: 'intimacy', band: 'affil', priority: 16, slots: ['ACTOR'], ptp: false,
    bandNote: 'Intimacy pressure should beat generic work when gates and suppressors allow it, but remain below basic embodied maintenance.',
    blurb: 'The body asks for the kind of connection that is not conversation.',
    gate: A(
      need('intimacy', 72),
      N(intimSupp()),
      cooldown('intimacy_fulfilled', 'actor', 8),
      cooldown('intimacy_pursued', 'actor', 8),
      cooldown('intimacy_partial', 'actor', 8),
      cooldown('intimacy_deferred', 'actor', 8),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'wounded')),
      N(eph('actor', 'grieving')),
    ),
    branches: [
      { label: 'Spend private time with an established partner', mag: 0.32, when: A(A(place('actor', 'dwelling'), residesHere()), partnerColo()),
        does: 'activity → "spending private time with partner"; fulfills `intimacy`, quality `established_partner`', event: 'intimacy_fulfilled',
        delta: { 'character.current_activity': 'spending private time with partner', 'need.fulfill': 'intimacy · established_partner' },
        stub: '{actor} closes the door on the day and lets private time with an established partner answer a need the public world has no claim on.' },
      { label: 'Visit a place where compatible company gathers', mag: 0.48, when: A(O(place('actor', 'entertainment'), place('actor', 'meeting')), need('intimacy', 168), N(tag('actor', 'partnered_exclusively'))),
        does: 'activity → "seeking compatible company"; fulfills `intimacy`, quality `pursued_possibility`, discharge 24', event: 'intimacy_pursued',
        delta: { 'character.current_activity': 'seeking compatible company', 'need.fulfill': 'intimacy · pursued_possibility · 24' },
        stub: '{actor} goes to the kind of place where someone like them might meet someone they would want to meet, alert to the possibility without presuming the outcome.' },
      { label: 'Engage contracted intimate company', mag: 0.28, when: A(O(place('actor', 'commerce'), place('actor', 'entertainment')), outPair('actor', 'contact:intimate'), N(tag('actor', 'partnered_exclusively')), N(anyTag('actor', ['vow_of_celibacy', 'religiously_abstinent', 'ethically_opposed_to_contracted_intimacy']))),
        does: 'activity → "engaging contracted intimate company"; fulfills `intimacy`, quality `contracted_companion`', event: 'intimacy_fulfilled',
        delta: { 'character.current_activity': 'engaging contracted intimate company', 'need.fulfill': 'intimacy · contracted_companion' },
        stub: '{actor} arranges what can be arranged, in one of the places where the transaction is understood by everyone involved and made ordinary by that clarity.' },
      { label: 'Attend to the need in private', mag: 0.06, when: A(O(place('actor', 'dwelling'), place('actor', 'place_restricted')), N(othersColo(1))),
        does: 'activity → "private personal time"; fulfills `intimacy`, quality `private_solo`, discharge 48', event: 'intimacy_partial',
        delta: { 'character.current_activity': 'private personal time', 'need.fulfill': 'intimacy · private_solo · 48' },
        stub: '{actor} attends to the body\u2019s quieter demands in private — an unremarkable hour the rest of the world has no business knowing about.' },
      { label: 'Let the want stay where it is', mag: 0.1, when: ALWAYS,
        does: 'activity → "carrying an unaddressed want"', event: 'intimacy_deferred',
        delta: { 'character.current_activity': 'carrying an unaddressed want' },
        stub: '{actor} does not pursue what the body is asking for — the wrong company, the wrong hour, the wrong life — and the want stays where it has been for a while now.' },
    ],
  },
  {
    id: 'TEND_CRAFT', tid: 'tend_craft', band: 'project', priority: 15, slots: ['ACTOR'], ptp: false,
    bandNote: 'Craft is the low-pressure identity/project floor and intentionally sits just above generic work.',
    blurb: 'A small act of care for the work that defines them.',
    gate: A(
      anyTag('actor', CRAFT_TAGS, 'actor has any craft-identity tag'),
      cooldown('craft_tended', 'actor', 4),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'wounded')),
      N(eph('actor', 'grieving')),
    ),
    branches: [
      { label: 'Put real money into the craft', mag: 0.18, when: resGte('wealthy'),
        does: 'activity → "investing in the craft"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'investing in the craft', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} spends on the work the way only someone with money can: the proper materials instead of the workable ones, the commissioned part instead of the salvaged one, the bought afternoon of uninterrupted attention.' },
      { label: 'Make the weapon ready for what comes next', mag: 0.18, when: anyTag('actor', ['combat_trained', 'soldier', 'warrior', 'fighter']),
        does: 'activity → "making the weapon ready"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'making the weapon ready', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} takes the weapon apart with the slow patience of someone who has done this enough times to know the geometry of each piece by feel, and puts it back together the same way, attentive to small things only they will notice.' },
      { label: 'Lay hands on the arcane work-in-progress', mag: 0.18, when: tag('actor', 'arcane_caster'),
        does: 'activity → "tending arcane work"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'tending arcane work', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} spends an unhurried hour with whatever is currently between their hands and the world\u2019s underlying grammar.' },
      { label: 'Maintain and improve the tools of the trade', mag: 0.18, when: anyTag('actor', ['engineer', 'mechanic', 'tinkerer', 'hacker', 'artificer']),
        does: 'activity → "maintaining equipment"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'maintaining equipment', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} attends to the equipment — the part that\u2019s been annoying them for weeks, the upgrade they keep meaning to install, the calibration that\u2019s been just slightly off — and emerges with the tools a small degree better than they were.' },
      { label: 'Run through the work that keeps the work possible', mag: 0.18, when: anyTag('actor', ['musician', 'dancer', 'performer', 'artist', 'writer', 'artisan']),
        does: 'activity → "practicing the unseen work"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'practicing the unseen work', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} works through the practice that no one will ever see — the scales, the exercises, the small motions that the public version of the art rests on.' },
      { label: 'Move the body through its daily reckoning', mag: 0.18, when: anyTag('actor', ['athlete', 'martial_artist', 'ranger', 'scout', 'monk']),
        does: 'activity → "conditioning the body"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'conditioning the body', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} puts the body through its daily reckoning — the run, the forms, the small punishments that keep the body ready for whatever the next demand will be.' },
      { label: 'Tend the small shop\u2019s quiet machinery', mag: 0.18, when: anyTag('actor', ['keeps_shop', 'merchant', 'innkeeper', 'trader']),
        does: 'activity → "tending the shop\u2019s rhythms"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'tending the shop\u2019s rhythms', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} does the things a place of business needs in order to keep being a place of business.' },
      { label: 'Keep the household running', mag: 0.18, when: anyTag('actor', ['domestic_role', 'cares_for_household', 'matriarch', 'patriarch']),
        does: 'activity → "tending the household"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'tending the household', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} does the work that holds a household together — the meals, the cleaning, the small attentions no one particularly thanks anyone for but whose absence would be felt immediately.' },
      { label: 'Return to the unfinished study', mag: 0.18, when: anyTag('actor', ['scholar', 'researcher', 'academic', 'loremaster']),
        does: 'activity → "advancing the long study"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'advancing the long study', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} returns to the long work that is always almost but never finished, and gives the work another quiet evening of the only thing it really needs.' },
      { label: 'Take a small action of care for the work that is theirs', mag: 0.12, when: ALWAYS,
        does: 'activity → "tending the work that is theirs"; adds `recently_tended_craft`', event: 'craft_tended',
        delta: { 'character.current_activity': 'tending the work that is theirs', 'entity_tags.add': ['recently_tended_craft'] },
        stub: '{actor} does a small thing for the work that defines them — they would not call it that, probably, but that is what it is — and the day is briefly better for it.' },
    ],
  },
  {
    id: 'WORK', tid: 'work', band: 'routine', priority: 14, slots: ['ACTOR'], ptp: false,
    blurb: 'The recurring work that keeps a life, household, or organization functioning.',
    gate: A(
      O(A(anchorHas('work'), anchorDue('work'), anchorAt('work')), tag('actor', 'work_obligation'), anyTag('actor', ['domestic_role', 'cares_for_household', 'field_worker'])),
      N(inTransit()),
      cooldown('work_performed', 'actor', 4),
      cooldown('household_work_performed', 'actor', 4),
      N(inPair('actor', 'hunting')),
      N(eph('actor', 'wounded')),
      N(eph('actor', 'grieving')),
    ),
    branches: [
      { label: 'Take whatever paying work the day offers', mag: 0.2, when: resLt('poor'),
        does: 'activity → "scraping together day labor"', event: 'work_performed',
        delta: { 'character.current_activity': 'scraping together day labor' },
        stub: '{actor} cannot afford the luxury of work that matches who they are. They take what the day pays for — hauling, queueing, standing in for someone luckier — and count the result in meals, not meaning.' },
      { label: 'Direct the work rather than perform it', mag: 0.16, when: resGte('wealthy'),
        does: 'activity → "directing the work of others"', event: 'work_performed',
        delta: { 'character.current_activity': 'directing the work of others' },
        stub: '{actor} does not stand a shift; they decide what the shifts are for.' },
      { label: 'Work a public-facing shift', mag: 0.18, when: O(O(place('actor', 'administration'), place('actor', 'craft'), place('actor', 'military'), place('actor', 'place_medical'), place('actor', 'production')), place('actor', 'commerce'), anyTag('actor', ['keeps_shop', 'merchant', 'innkeeper', 'trader'])),
        does: 'activity → "working a public-facing shift"', event: 'work_performed',
        delta: { 'character.current_activity': 'working a public-facing shift' },
        stub: '{actor} gives the day to work that other people can see: the counter, the ledger, the bargaining, the small maintenance of trust that keeps trade from becoming chaos.' },
      { label: 'Handle field or maintenance work', mag: 0.2, when: O(O(place('actor', 'craft'), place('actor', 'military'), place('actor', 'production')), tag('actor', 'field_worker')),
        does: 'activity → "handling field maintenance work"', event: 'work_performed',
        delta: { 'character.current_activity': 'handling field maintenance work' },
        stub: '{actor} spends the hour in practical labor: repairs, inspection, hauling, checking systems whose importance only becomes visible when they fail.' },
      { label: 'Keep administrative obligations moving', mag: 0.16, when: O(place('actor', 'administration'), anyTag('actor', ['researcher', 'academic', 'soldier']), factionSenior()),
        does: 'activity → "handling administrative work"', event: 'work_performed',
        delta: { 'character.current_activity': 'handling administrative work' },
        stub: '{actor} moves necessary work through the quiet machinery: forms, messages, rosters, notes, approvals, the kind of paper trail that decides what can happen tomorrow.' },
      { label: 'Do the labor that holds a household together', mag: 0.18, when: anyTag('actor', ['domestic_role', 'cares_for_household']),
        does: 'activity → "doing household work"', event: 'household_work_performed',
        delta: { 'character.current_activity': 'doing household work' },
        stub: '{actor} does household work with the competence of someone who knows that ordinary life is not self-maintaining.' },
      { label: 'Keep the obligation from slipping', mag: 0.1, when: ALWAYS,
        does: 'activity → "keeping obligations current"', event: 'work_performed',
        delta: { 'character.current_activity': 'keeping obligations current' },
        stub: '{actor} takes care of the work that would otherwise start to fray — not enough to become a story by itself, but enough that the world does not have to break here today.' },
    ],
  },
  {
    id: 'MAINTAIN_COVER', tid: 'maintain_cover', band: 'crisis', priority: 0, slots: ['ACTOR'], ptp: false,
    bandNote: 'priority-order exempt: intentionally a floor package that should not force routine needs or story obligations to justify outranking it.',
    blurb: 'Specific public-cover maintenance, not a universal fallback.',
    gate: A(
      hydrated(),
      N(constrained()),
      N(hiddenOff()),
      N(inTransit()),
      anyCur('actor', ['broker', 'cover_identity', 'fixer', 'operative', 'public_role', 'undercover']),
      O(place('actor', 'urban_dense'), place('actor', 'place_open'), place('actor', 'transit'), place('actor', 'commerce'), place('actor', 'meeting')),
      cooldown('maintain_cover', 'actor', 6),
    ),
    branches: [
      { label: 'Be seen exactly where they are expected', mag: 0.14, when: fameGte('renowned'),
        does: 'activity → "performing the expected public pattern"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'performing the expected public pattern' },
        stub: '{actor} cannot be nobody, so they are conspicuously, boringly themselves: the usual table, the usual hours, the usual complaints — a public pattern so consistent that nobody thinks to ask what it covers.' },
      { label: 'Run a low-level courier job', mag: 0.16, when: A(O(place('actor', 'urban_dense'), place('actor', 'place_open'), place('actor', 'transit'), place('actor', 'commerce'), place('actor', 'meeting')), pubFlow(), fameLt('renowned')),
        does: 'activity → "running low-level cover work"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'running low-level cover work' },
        stub: '{actor} picks up a benign data packet, walks it across the district, and earns just enough to register as ordinary.' },
      { label: 'Maintain a specific cover identity', mag: 0.14, when: anyCur('actor', ['cover_identity', 'public_role', 'undercover']),
        does: 'activity → "maintaining cover identity"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'maintaining cover identity' },
        stub: '{actor} services the identity that keeps questions from forming: one believable errand, one ordinary exchange, one small proof that the mask has a life of its own.' },
      { label: 'Keep a public role legible', mag: 0.12, when: anyCur('actor', ['broker', 'fixer', 'operative']),
        does: 'activity → "keeping public role legible"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'keeping public role legible' },
        stub: '{actor} keeps their visible role legible to the people who expect to see it — enough routine, enough responsiveness, enough plausible friction to look like a life.' },
      { label: 'Drift through public space', mag: 0.1, when: A(pubFlow(), fameLt('renowned')),
        does: 'activity → "maintaining public cover"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'maintaining public cover' },
        stub: '{actor} moves through public space at the pace of someone with somewhere to be, generating forgettable civilian noise.' },
      { label: 'Keep the ledger plausible from a fixed post', mag: 0.08, when: ALWAYS,
        does: 'activity → "maintaining fixed cover"', event: 'maintain_cover',
        delta: { 'character.current_activity': 'maintaining fixed cover' },
        stub: '{actor} makes no dramatic move. They answer what must be answered, neglect what can be neglected, and keep their visible life plausible without pretending to be free of it.' },
    ],
  },
];

export const TEMPLATE_BY_ID = Object.fromEntries(TEMPLATES.map((t) => [t.id, t]));
export const ACTOR_ONLY = TEMPLATES.filter((t) => t.slots.length === 1);
export const TWO_PARTY = TEMPLATES.filter((t) => t.slots.length === 2);

// Event types consumed by gates but emitted by no branch — the dead-arm lint.
export const DEAD_GATE_ARMS = [
  { event: 'threat_issued',      consumers: ['WARN_ALLY', 'PROTECT_KIN', 'CONSULT_RIVAL', 'SURVEIL'] },
  { event: 'compliance_alert',   consumers: ['EVADE_PURSUERS', 'WARN_ALLY', 'CONSULT_RIVAL', 'HIDE (branch)'] },
  { event: 'faction_realignment', consumers: ['CONSULT_RIVAL'] },
  { event: 'encoded_message',    consumers: ['HONOR_DEBT'] },
];

// ------------------------------------------------------------ seed tick ----

export function baseWorldState() {
  return {
    slot: 'save_02',
    anchor: 108,
    windowChunks: 30,
    baseAnchor: 108,
    baseWorldTime: Date.UTC(2073, 9, 14, 21, 40) / 1000, // 2073-10-14 21:40
    weatherByTick: (t) => (t >= 104 && t <= 112 ? 'rain' : 'clear'),
    entities: {
      victor: { id: 'victor', name: 'Victor Sato', onScreen: false, place: 'glow', fame: 'local', resources: 'comfortable',
        tags: ['informant_handler', 'signal_operator', 'undercover', 'work_obligation'], ephemerals: ['intelligence_asset_active'],
        needs: { sleep: 6, hunger: 5, thirst: 1.5, socialize: 30, intimacy: 20 }, resolveDest: true },
      lansky: { id: 'lansky', name: 'Lansky', onScreen: false, place: 'glow', fame: 'known', resources: 'comfortable',
        tags: ['broker', 'reserved'], ephemerals: [],
        needs: { sleep: 5, hunger: 3.5, thirst: 1, socialize: 20, intimacy: 40 }, resolveDest: true },
      asmodeus: { id: 'asmodeus', name: 'Asmodeus', onScreen: false, place: 'ashgrid', fame: 'local', resources: 'comfortable',
        tags: ['vendetta_holder', 'violent_history', 'hacker', 'safehouse_operator', 'off_grid'], ephemerals: ['grudge_active', 'cns_stimulated', 'reputation_compromised'],
        needs: { sleep: 14, hunger: 3, thirst: 1.2, socialize: 12, intimacy: 80 }, resolveDest: true },
      celia: { id: 'celia', name: 'Celia', onScreen: false, place: 'glow', fame: 'local', resources: 'struggling',
        tags: ['fugitive', 'paranoid'], ephemerals: ['intelligence_asset_active', 'wounded'],
        needs: { sleep: 49.5, hunger: 3.1, thirst: 1.8, socialize: 26, intimacy: 15 }, resolveDest: true },
      juno: { id: 'juno', name: 'Juno', onScreen: false, place: 'remembrance', fame: 'local', resources: 'poor',
        tags: ['combat_trained'], ephemerals: ['grieving', 'recently_violent', 'grudge_active'],
        needs: { sleep: 26, hunger: 6, thirst: 2.5, socialize: 18, intimacy: 30 }, resolveDest: true },
      talon: { id: 'talon', name: 'Talon', onScreen: false, place: 'rootline', fame: 'local', resources: 'struggling',
        tags: ['route_familiar', 'combat_trained'], ephemerals: ['wounded', 'grudge_active', 'recently_violent'],
        needs: { sleep: 18, hunger: 17, thirst: 3.8, socialize: 40, intimacy: 25 }, resolveDest: true },
      alex: { id: 'alex', name: 'Alex', onScreen: true, place: 'glow', fame: 'known', resources: 'comfortable',
        tags: ['seeking_identity', 'ghostprint_active'], ephemerals: [],
        needs: { sleep: 7, hunger: 4.5, thirst: 2.1, socialize: 5, intimacy: 12 }, resolveDest: true },
      pete: { id: 'pete', name: 'Pete', onScreen: true, place: 'glow', fame: 'local', resources: 'struggling',
        tags: ['hacker'], ephemerals: [],
        needs: { sleep: 9, hunger: 6, thirst: 9, socialize: 4, intimacy: 20 }, resolveDest: true },
      alina: { id: 'alina', name: 'Alina', onScreen: true, place: 'glow', fame: 'local', resources: 'comfortable',
        tags: ['bodyform:android', 'signal_operator'], ephemerals: [],
        needs: { sleep: 0, hunger: 0, thirst: 0, socialize: 14, intimacy: 0 }, resolveDest: true },
    },
    pairTags: [
      { from: 'victor', to: 'talon', tag: 'hunting' },
      { from: 'talon', to: 'asmodeus', tag: 'contact:lodging' },
      { from: 'juno', to: 'asmodeus', tag: 'contact:social' },
    ],
    relationships: [
      { a: 'victor', b: 'celia', typesAB: ['handler', 'rival'], typesBA: ['asset', 'rival'], trustAB: 2, trustBA: -1 },
      { a: 'victor', b: 'talon', typesAB: ['enemy'], typesBA: ['enemy'], trustAB: -3, trustBA: -4 },
      { a: 'asmodeus', b: 'talon', typesAB: ['comrade'], typesBA: ['comrade'], trustAB: 2, trustBA: 3 },
      { a: 'juno', b: 'talon', typesAB: ['comrade'], typesBA: ['comrade'], trustAB: 3, trustBA: 3 },
      { a: 'asmodeus', b: 'alex', typesAB: ['enemy'], typesBA: ['enemy'], trustAB: -4, trustBA: -2 },
      { a: 'victor', b: 'alex', typesAB: ['rival'], typesBA: ['rival'], trustAB: -2, trustBA: -1 },
      { a: 'celia', b: 'alex', typesAB: ['rival'], typesBA: ['rival'], trustAB: -1, trustBA: 0 },
      { a: 'lansky', b: 'alex', typesAB: ['ally'], typesBA: ['ally'], trustAB: 0, trustBA: 0 },
    ],
    events: [
      { type: 'threat_issued', tick: 107, target: 'talon' },
      { type: 'compliance_alert', tick: 106, target: 'celia' },
      { type: 'surveillance_performed', tick: 103, pair: ['celia', 'victor'] },
      { type: 'tended_wound', tick: 107, pair: ['victor', 'celia'] },
      { type: 'intel_reviewed', tick: 104, pair: ['lansky', 'alex'] },
      { type: 'maintain_cover', tick: 105, actor: 'lansky' },
      { type: 'encoded_message', tick: 92, target: 'asmodeus' },
      { type: 'evade_pursuit', tick: 96, actor: 'talon' },
      { type: 'mourning_act', tick: 101, actor: 'juno' },
    ],
    overrides: [],
  };
}

// Tag provenance for the hover-audit (per-row, not global).
// solid = exact (source chunk + world time), ring = approximate (retrograde
// backfill epoch), hollow = unknowable (skald_inline, NULL world time).
export const PROVENANCE = {
  'talon:wounded': { dot: 'hollow', src: 'skald_inline', note: 'NULL world time' },
  'asmodeus:cns_stimulated': { dot: 'hollow', src: 'skald_inline', note: 'NULL world time' },
  'asmodeus:grudge_active': { dot: 'solid', src: 'resolver', note: 'chunk 0089' },
  'juno:grieving': { dot: 'solid', src: 'resolver', note: 'chunk 0094' },
  'juno:grudge_active': { dot: 'solid', src: 'resolver', note: 'chunk 0095' },
  'talon:grudge_active': { dot: 'solid', src: 'resolver', note: 'chunk 0095' },
  'celia:wounded': { dot: 'solid', src: 'resolver', note: 'chunk 0102' },
  'victor:intelligence_asset_active': { dot: 'solid', src: 'resolver', note: 'chunk 0099' },
  'celia:intelligence_asset_active': { dot: 'solid', src: 'resolver', note: 'chunk 0099' },
};
export function provenanceFor(entityId, tagName) {
  return PROVENANCE[entityId + ':' + tagName] || { dot: 'ring', src: 'retrograde', note: 'backfill epoch' };
}

// ------------------------------------------------------------- clock ----

export function worldTimeFor(state) {
  const dTicks = state.anchor - state.baseAnchor;
  const secs = state.baseWorldTime + dTicks * 45 * 60;
  const d = new Date(secs * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return {
    iso: `2073-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`,
    hours: d.getUTCHours() + d.getUTCMinutes() / 60,
  };
}
export function timeOfDayFor(state) {
  const h = worldTimeFor(state).hours;
  if (h >= 5 && h < 12) return 'morning';
  if (h >= 12 && h < 17) return 'afternoon';
  if (h >= 17 && h < 21) return 'evening';
  return 'night';
}

// ------------------------------------------------------ override layer ----

export function applyOverrides(base, overrides, anchor) {
  const s = JSON.parse(JSON.stringify({ ...base, weatherByTick: undefined }));
  s.weatherByTick = base.weatherByTick;
  s.anchor = anchor != null ? anchor : base.anchor;
  s.overrides = overrides || [];
  // need accrual with anchor drift (rate 1.0/hr, 0.75h per tick, clamped ≥0)
  const drift = (s.anchor - base.baseAnchor) * 0.75;
  for (const e of Object.values(s.entities)) {
    for (const n of NEEDS) e.needs[n] = Math.max(0, +(e.needs[n] + drift).toFixed(1));
  }
  for (const ov of s.overrides) {
    if (ov.kind === 'tag') {
      const e = s.entities[ov.entity];
      const list = ov.eph ? e.ephemerals : e.tags;
      const i = list.indexOf(ov.tag);
      if (ov.on && i < 0) list.push(ov.tag);
      if (!ov.on && i >= 0) list.splice(i, 1);
    } else if (ov.kind === 'pairTag') {
      const i = s.pairTags.findIndex((p) => p.from === ov.from && p.to === ov.to && p.tag === ov.tag);
      if (ov.on && i < 0) s.pairTags.push({ from: ov.from, to: ov.to, tag: ov.tag });
      if (!ov.on && i >= 0) s.pairTags.splice(i, 1);
    } else if (ov.kind === 'need') {
      s.entities[ov.entity].needs[ov.need] = ov.value;
    } else if (ov.kind === 'move') {
      s.entities[ov.entity].place = ov.place;
    } else if (ov.kind === 'event') {
      s.events.push({ type: ov.type, tick: s.anchor - (ov.ago ?? 1), target: ov.target });
    }
  }
  return s;
}

// --------------------------------------------------------- evaluation ----

function ctx(state) {
  return { state, tod: timeOfDayFor(state), weather: state.weatherByTick(state.anchor), tick: state.anchor };
}

function evalLeaf(leaf, c, b) {
  const S = c.state;
  const who = (w) => (w === 'target' ? b.TARGET : b.ACTOR);
  const ent = (w) => S.entities[who(w)];
  const trust = (x, y) => {
    for (const r of S.relationships) {
      if (r.a === x && r.b === y) return r.trustAB;
      if (r.a === y && r.b === x) return r.trustBA;
    }
    return 0;
  };
  const relTypes = (x, y) => { // directional: types x holds toward y
    for (const r of S.relationships) {
      if (r.a === x && r.b === y) return r.typesAB;
      if (r.a === y && r.b === x) return r.typesBA;
    }
    return [];
  };
  const relUnion = (x, y) => [...new Set([...relTypes(x, y), ...relTypes(y, x)])];
  const hasIn = (id, t) => S.pairTags.some((p) => p.to === id && p.tag === t);
  const hasOut = (id, t) => S.pairTags.some((p) => p.from === id && p.tag === t);
  const cur = (e) => [...e.tags, ...e.ephemerals];
  const placeOf = (e) => PLACES[e.place];
  const fmt = (v) => (typeof v === 'number' ? +v.toFixed(1) : v);
  let pass = false, ev = '', reads = [];

  switch (leaf.p) {
    case 'hydrated': pass = true; ev = `window ${S.windowChunks} chunks`; break;
    case 'tag': { const e = ent(leaf.w); pass = e.tags.includes(leaf.t); ev = pass ? 'present' : 'absent'; reads = [leaf.t]; break; }
    case 'eph': { const e = ent(leaf.w); pass = e.ephemerals.includes(leaf.t); ev = pass ? 'present' : 'absent'; reads = [leaf.t]; break; }
    case 'anyTag': { const e = ent(leaf.w); const hit = leaf.list.find((t) => e.tags.includes(t)); pass = !!hit; ev = hit ? `matched: ${hit}` : 'no member present'; reads = leaf.list; break; }
    case 'anyCur': { const e = ent(leaf.w); const hit = leaf.list.find((t) => cur(e).includes(t)); pass = !!hit; ev = hit ? `matched: ${hit}` : 'no member present'; reads = leaf.list; break; }
    case 'inPair': { const id = who(leaf.w); const srcs = S.pairTags.filter((p) => p.to === id && p.tag === leaf.t); pass = srcs.length > 0; ev = pass ? `from ${srcs.map((p) => S.entities[p.from].name).join(', ')}` : 'none inbound'; reads = [leaf.t]; break; }
    case 'outPair': { const id = who(leaf.w); const dsts = S.pairTags.filter((p) => p.from === id && p.tag === leaf.t); pass = dsts.length > 0; ev = pass ? `to ${dsts.map((p) => S.entities[p.to].name).join(', ')}` : 'none outbound'; reads = [leaf.t]; break; }
    case 'residesHere': { pass = S.pairTags.some((p) => p.from === b.ACTOR && p.tag === 'resides_at' && p.to === ent('actor').place); ev = pass ? 'resides here' : 'not their residence'; reads = ['resides_at']; break; }
    case 'relShared': { const ts = relUnion(b.ACTOR, b.TARGET); pass = ts.includes(leaf.t); ev = ts.length ? `edge: {${ts.join(', ')}}` : 'no edge'; break; }
    case 'relDir': { const ts = relTypes(b.ACTOR, b.TARGET); pass = ts.includes(leaf.t); ev = ts.length ? `actor→target: {${ts.join(', ')}}` : 'no directed edge'; break; }
    case 'relDirRev': { const ts = relTypes(b.TARGET, b.ACTOR); pass = ts.includes(leaf.t); ev = ts.length ? `target→actor: {${ts.join(', ')}}` : 'no directed edge'; break; }
    case 'trustLt': { const v = trust(b.ACTOR, b.TARGET); pass = v < leaf.v; ev = `trust ${v} ${pass ? '<' : '≥'} ${leaf.v}`; break; }
    case 'trustGte': { const v = trust(b.ACTOR, b.TARGET); pass = v >= leaf.v; ev = `trust ${v} ${pass ? '≥' : '<'} ${leaf.v}`; break; }
    case 'mutualWarm': { const a2 = trust(b.ACTOR, b.TARGET), b2 = trust(b.TARGET, b.ACTOR); pass = a2 >= 2 && b2 >= 2; ev = `trust ${a2} / ${b2}`; break; }
    case 'trustLoaded': { const a2 = trust(b.ACTOR, b.TARGET), b2 = trust(b.TARGET, b.ACTOR); pass = Math.abs(a2 - b2) >= 3 || a2 <= -2 || b2 <= -2; ev = `trust ${a2} / ${b2}`; break; }
    case 'dramatic': {
      const aH = FAMILIES.DRAMATIC_CONTACT_TAGS.find((t) => cur(ent('actor')).includes(t));
      const tH = b.TARGET ? FAMILIES.DRAMATIC_CONTACT_TAGS.find((t) => cur(ent('target')).includes(t)) : null;
      const hunted = b.TARGET && hasIn(b.TARGET, 'hunting');
      pass = !!(aH || tH || hunted);
      ev = aH ? `actor ${aH} ∈ DRAMATIC_CONTACT` : tH ? `target ${tH} ∈ DRAMATIC_CONTACT` : hunted ? 'target has inbound hunting' : 'contact is ordinary';
      reads = FAMILIES.DRAMATIC_CONTACT_TAGS.concat(['hunting']); break;
    }
    case 'need': { const e = ent('actor'); const imm = NEED_IMMUNITY[leaf.nd].find((t) => cur(e).includes(t)); if (imm) { pass = false; ev = `immune (${imm})`; } else { const v = e.needs[leaf.nd]; pass = v >= leaf.v; ev = `${leaf.nd} debt ${fmt(v)} ${pass ? '≥' : '<'} ${leaf.v}`; } break; }
    case 'evRecent': {
      const hit = S.events.filter((e) => e.type === leaf.t && (c.tick - e.tick) <= leaf.within && (c.tick - e.tick) >= 0)
        .filter((e) => leaf.targeting === 'any' ? true : e.target === who(leaf.targeting));
      pass = hit.length > 0;
      const near = S.events.filter((e) => e.type === leaf.t && (leaf.targeting === 'any' || e.target === who(leaf.targeting))).sort((x, y) => y.tick - x.tick)[0];
      ev = pass ? `t${hit[0].tick} → ${c.tick - hit[0].tick} ≤ ${leaf.within}` : near ? `last t${near.tick} → ${c.tick - near.tick} > ${leaf.within}` : 'none in window';
      break;
    }
    case 'cooldown': {
      const match = S.events.filter((e) => e.type === leaf.t && (
        leaf.scope === 'pair' ? (e.pair && e.pair[0] === b.ACTOR && e.pair[1] === b.TARGET) : (e.actor === b.ACTOR)
      )).sort((x, y) => y.tick - x.tick)[0];
      if (!match) { pass = true; ev = 'none in window'; }
      else { const dt = c.tick - match.tick; pass = dt >= leaf.ticks; ev = `last t${match.tick} → ${dt} ${pass ? '≥' : '<'} ${leaf.ticks}`; }
      break;
    }
    case 'tod': pass = leaf.list.includes(c.tod); ev = c.tod; break;
    case 'weather': pass = leaf.list.includes(c.weather); ev = c.weather; break;
    case 'place': { const p = placeOf(ent(leaf.w)); pass = p.classes.includes(leaf.c); ev = `${p.name.split(' — ')[0]} {${p.classes.join(', ')}}`; break; }
    case 'colo': { pass = ent('actor').place === ent('target').place; ev = pass ? `both at ${placeOf(ent('actor')).name.split(' — ')[0]}` : `${placeOf(ent('actor')).name.split(' — ')[0]} vs ${placeOf(ent('target')).name.split(' — ')[0]}`; break; }
    case 'othersColo': { const id = who(leaf.w); const p = S.entities[id].place; const n = Object.values(S.entities).filter((e) => e.id !== id && e.place === p).length; pass = n >= leaf.n; ev = `${n} co-located`; break; }
    case 'othersGrieving': { const p = ent('actor').place; const n = Object.values(S.entities).filter((e) => e.id !== b.ACTOR && e.place === p && e.ephemerals.includes('grieving')).length; pass = n >= 1; ev = `${n} grieving co-located`; reads = ['grieving']; break; }
    case 'fameGte': { const e = ent('actor'); pass = FAME.indexOf(e.fame) >= FAME.indexOf(leaf.r); ev = `fame: ${e.fame}`; break; }
    case 'fameLt': { const e = ent('actor'); pass = FAME.indexOf(e.fame) < FAME.indexOf(leaf.r); ev = `fame: ${e.fame}`; break; }
    case 'resGte': { const e = ent('actor'); pass = RESOURCES.indexOf(e.resources) >= RESOURCES.indexOf(leaf.r); ev = `resources: ${e.resources}`; break; }
    case 'resLt': { const e = ent('actor'); pass = RESOURCES.indexOf(e.resources) < RESOURCES.indexOf(leaf.r); ev = `resources: ${e.resources}`; break; }
    case 'constrained': { const hit = FAMILIES.CONSTRAINED_TAGS.find((t) => cur(ent('actor')).includes(t)); pass = !!hit; ev = hit ? `matched: ${hit} ∈ CONSTRAINED` : 'unconstrained'; reads = FAMILIES.CONSTRAINED_TAGS; break; }
    case 'hiddenOff': { const hit = FAMILIES.HIDDEN_TAGS.find((t) => cur(ent('actor')).includes(t)); pass = !!hit; ev = hit ? `matched: ${hit} ∈ HIDDEN` : 'not hidden'; reads = FAMILIES.HIDDEN_TAGS; break; }
    case 'pubFlow': { const e = ent(leaf.w); const hit = FAMILIES.PUBLIC_MOBILITY_BLOCKERS.find((t) => cur(e).includes(t)); pass = !hit; ev = hit ? `blocked: ${hit} ∈ MOBILITY_BLOCKERS` : 'unblocked'; reads = FAMILIES.PUBLIC_MOBILITY_BLOCKERS; break; }
    case 'intimSupp': { const hit = FAMILIES.INTIMACY_SUPPRESSOR_TAGS.find((t) => cur(ent('actor')).includes(t)); pass = !!hit; ev = hit ? `matched: ${hit} ∈ INTIMACY_SUPPRESSOR` : 'no suppressor'; reads = FAMILIES.INTIMACY_SUPPRESSOR_TAGS; break; }
    case 'inTransit': { pass = !!(ent('actor').travel && ent('actor').travel.inTransit); ev = pass ? 'in transit' : 'not in transit'; break; }
    case 'hasDest': { pass = !!(ent('actor').travel && ent('actor').travel.dest); ev = pass ? `dest: ${ent('actor').travel.dest}` : 'no destination'; break; }
    case 'travProg': { const t = ent('actor').travel; const v = t ? t.progress || 0 : 0; pass = v >= leaf.v; ev = `progress ${v}`; break; }
    case 'travPurpose': { const t = ent('actor').travel; pass = !!t && t.purpose === leaf.v; ev = t ? `purpose: ${t.purpose || '—'}` : 'not traveling'; break; }
    case 'travRisk': { const t = ent('actor').travel; pass = !!t && leaf.list.includes(t.risk); ev = t ? `risk: ${t.risk || '—'}` : 'not traveling'; break; }
    case 'anchorHas': case 'anchorDue': case 'anchorAway': case 'anchorAt': case 'anchorResolves': {
      const anch = (ent('actor').routine || {})[leaf.k];
      if (leaf.p === 'anchorHas') { pass = !!anch; ev = anch ? 'anchor set' : 'no anchor (slot 2 backfill)'; }
      else if (!anch) { pass = false; ev = 'no anchor'; }
      else { pass = true; ev = 'anchor ok'; }
      break;
    }
    case 'partnerColo': { const p = ent('actor').place; const partner = S.relationships.find((r) => ((r.a === b.ACTOR && S.entities[r.b].place === p) || (r.b === b.ACTOR && S.entities[r.a].place === p)) && [...(r.typesAB || []), ...(r.typesBA || [])].includes('romantic')); pass = !!partner; ev = pass ? 'partner present' : 'no established partner co-located'; break; }
    case 'factionSenior': { pass = !!ent('actor').factionSenior; ev = pass ? 'status:senior+' : 'no senior standing'; break; }
    case 'resolveDest': { pass = !!ent('actor').resolveDest; ev = pass ? 'route graph resolves' : 'no destination resolvable'; break; }
    default: pass = false; ev = 'unknown predicate';
  }
  return { kind: 'leaf', p: leaf.p, prose: leaf.prose, pass, evidence: ev, reads };
}

export function evalNode(node, c, b) {
  if (!node) return null;
  if (!node.op) return evalLeaf(node, c, b);
  const children = node.children.map((ch) => evalNode(ch, c, b));
  let pass;
  if (node.op === 'AND') pass = children.every((x) => x.pass);
  else if (node.op === 'OR') pass = children.some((x) => x.pass);
  else pass = !children[0].pass;
  return { kind: 'op', op: node.op, pass, children };
}

function firstFailingLeaf(trace) {
  // walk the trace, return the shallowest failing leaf on the failure path
  if (!trace) return null;
  if (trace.kind === 'leaf') return trace.pass ? null : trace;
  if (trace.op === 'NOT') {
    if (trace.pass) return null;
    // NOT failed because child passed — report the child leaf that passed
    const passing = firstPassingLeaf(trace.children[0]);
    return passing ? { ...passing, negated: true } : null;
  }
  if (trace.pass) return null;
  if (trace.op === 'AND') { for (const ch of trace.children) { const f = firstFailingLeaf(ch); if (f) return f; } }
  if (trace.op === 'OR') { for (const ch of trace.children) { const f = firstFailingLeaf(ch); if (f) return f; } }
  return null;
}
function firstPassingLeaf(trace) {
  if (!trace) return null;
  if (trace.kind === 'leaf') return trace.pass ? trace : null;
  if (trace.op === 'NOT') return trace.pass ? firstFailingLeaf(trace.children[0]) : null;
  for (const ch of trace.children) { const f = firstPassingLeaf(ch); if (f) return f; }
  return null;
}
export { firstFailingLeaf, firstPassingLeaf };

function subst(text, c, b) {
  if (!text) return text;
  return text
    .replaceAll('{actor}', c.state.entities[b.ACTOR].name)
    .replaceAll('{target}', b.TARGET ? c.state.entities[b.TARGET].name : '{target}');
}

export function explainTemplate(tpl, c, b) {
  const gate = evalNode(tpl.gate, c, b);
  const out = {
    id: tpl.id, tid: tpl.tid, name: tpl.id, band: tpl.band, priority: tpl.priority,
    slots: tpl.slots, ptp: tpl.ptp, blurb: tpl.blurb, bandNote: tpl.bandNote || null,
    bindings: { ACTOR: b.ACTOR, TARGET: b.TARGET || null },
    gate, gatePassed: gate.pass, fired: false, branches: [], resolution: null,
    failLeaf: gate.pass ? null : firstFailingLeaf(gate),
  };
  let selected = -1;
  out.branches = tpl.branches.map((br, i) => {
    if (!gate.pass || selected >= 0) {
      return { i, label: br.label, mag: br.mag, considered: false, passed: null, trace: null, selected: false, failLeaf: null };
    }
    const trace = br.when ? evalNode(br.when, c, b) : { kind: 'leaf', p: 'always', prose: '(always)', pass: true, evidence: 'terminal fallback', reads: [] };
    const passed = trace.pass;
    if (passed) selected = i;
    return { i, label: br.label, mag: br.mag, considered: true, passed, trace, selected: passed, failLeaf: passed ? null : firstFailingLeaf(trace) };
  });
  if (gate.pass && selected >= 0) {
    const br = tpl.branches[selected];
    out.fired = true;
    out.resolution = {
      branchLabel: br.label, magnitude: br.mag, eventType: br.event,
      stub: subst(br.stub, c, b), does: br.does, delta: br.delta,
      pressureStub: br.pressure ? subst(br.pressure, c, b) : null,
      bindingHash: 'sha256:' + [tpl.tid, b.ACTOR, b.TARGET || ''].join(':'),
    };
  }
  return out;
}

export function explainStack(templates, c, b) {
  // priority desc, authored tuple order for ties (array order IS authored order)
  const rows = templates.map((t) => explainTemplate(t, c, b));
  let winner = null;
  for (const r of rows) {
    if (r.fired && !winner) { r.status = 'winner'; winner = r; }
    else if (r.fired) r.status = 'shadowed';
    else r.status = 'gate_failed';
  }
  // priority ties among fired templates
  for (const r of rows) {
    if (!r.fired) continue;
    const peers = rows.filter((x) => x.fired && x !== r && x.priority === r.priority);
    r.tie = peers.length ? peers.map((p) => p.id) : null;
  }
  return { rows, winner };
}

// -------------------------------------------------------- the resolver ----

export function resolveTick(state) {
  const c = ctx(state);
  const offscreen = Object.values(state.entities).filter((e) => !e.onScreen);
  const onscreen = Object.values(state.entities).filter((e) => e.onScreen);
  const edgesOf = (id) => state.relationships.filter((r) => r.a === id || r.b === id)
    .map((r) => (r.a === id ? r.b : r.a));

  const groups = offscreen.map((actor) => {
    const b = { ACTOR: actor.id };
    const solo = explainStack(ACTOR_ONLY, c, b);
    const partners = edgesOf(actor.id);
    const offPartners = partners.filter((p) => !state.entities[p].onScreen);
    const onPartners = partners.filter((p) => state.entities[p].onScreen);

    const pairs = offPartners.map((tid) => {
      const pb = { ACTOR: actor.id, TARGET: tid };
      const stack = explainStack(TWO_PARTY, c, pb);
      return { target: tid, ...stack };
    });

    // two-party templates with no off-screen target bound at all → not applicable
    const notApplicable = offPartners.length === 0
      ? TWO_PARTY.map((t) => ({ id: t.id, tid: t.tid, band: t.band, priority: t.priority, status: 'not_applicable', slots: t.slots }))
      : [];

    const pressures = [];
    for (const tid of onPartners) {
      const pb = { ACTOR: actor.id, TARGET: tid };
      const stack = explainStack(TWO_PARTY, c, pb);
      if (stack.winner) pressures.push({ target: tid, ...stack });
    }

    const fires = [solo.winner, ...pairs.map((p) => p.winner)].filter(Boolean);
    return { actor: actor.id, solo, pairs, pressures, notApplicable, gap: fires.length === 0 && pressures.length === 0 };
  });

  // present-target need pressures (pseudo-templates, outside the catalog)
  const needPressures = [];
  for (const e of onscreen) {
    for (const nd of NEEDS) {
      if (NEED_IMMUNITY[nd].some((t) => [...e.tags, ...e.ephemerals].includes(t))) continue;
      const v = e.needs[nd];
      const th = NEED_THRESHOLDS[nd];
      let level = 0, name = null;
      for (const [lv, nm] of [[4, 'critical'], [3, 'severe'], [2, 'moderate'], [1, 'mild']]) {
        if (v >= th[nm]) { level = lv; name = nm; break; }
      }
      if (level >= 2) {
        needPressures.push({
          pseudo: true, id: `${nd}_need_pressure`, band: 'embodied',
          priority: NEED_PRESSURE_PRIORITY[nd], target: e.id, need: nd, debt: +v.toFixed(1),
          severity: name, level, magnitude: Math.min(0.85, 0.35 + level * 0.10),
        });
      }
    }
  }

  return { groups, needPressures, tod: c.tod, weather: c.weather, tick: c.tick };
}

// Reciprocal detection: pure post-pass over winners, keyed on reversed (actor, target)
export function reciprocalPairs(resolved) {
  const winners = [];
  for (const g of resolved.groups) for (const p of g.pairs) if (p.winner) winners.push({ from: g.actor, to: p.target, tpl: p.winner.id });
  const out = [];
  for (const w of winners) {
    const rev = winners.find((x) => x.from === w.to && x.to === w.from);
    if (rev && w.from < w.to) out.push({ a: w.from, b: w.to, tplA: w.tpl, tplB: rev.tpl });
  }
  return out;
}

// ------------------------------------------------- window batch stats ----
// Invented-but-plausible coverage analysis over the loaded window (79→108),
// shaped like the real save_02 pathologies.

export const WINDOW_STATS = {
  window: '79 → 108',
  ticks: 30,
  neverWin: ['MAINTAIN_COVER', 'CONSULT_RIVAL', 'ROUTINE_COMMUTE', 'INTIMACY', 'HONOR_DEBT'],
  dominant: [
    { id: 'HIDE', share: 0.61 },
    { id: 'TEND_CRAFT', share: 0.12 },
    { id: 'WORK', share: 0.09 },
    { id: 'SURVEIL', share: 0.07 },
  ],
  dataQuality: [
    { kind: 'null_world_time', text: '22 / 35 resolver bestowals carry NULL applied_at_world_time', sev: 'warn' },
    { kind: 'wall_clock_epoch', text: 'retrograde epoch: world-times 2073-06 → 2073-10 written at one wall-clock instant', sev: 'warn' },
    { kind: 'clearance_log', text: '398 / 403 cleared tag rows have no clearance-log entry', sev: 'warn' },
    { kind: 'pair_clears', text: 'pair-tag clears are unlogged on every path', sev: 'error' },
    { kind: 'routine_anchors', text: 'no routine anchors seeded in slot 2 — ROUTINE_COMMUTE / WORK anchor arms unreachable', sev: 'info' },
  ],
};

// ------------------------------------------------------------ self test ----

export function selfTest() {
  const s = applyOverrides(baseWorldState(), [], 108);
  const r = resolveTick(s);
  const g = Object.fromEntries(r.groups.map((x) => [x.actor, x]));
  const errs = [];
  const expectWinner = (grp, tpl, branch) => {
    const w = grp.solo.winner;
    if (!w) { errs.push(`${grp.actor}: expected solo winner ${tpl}, got none`); return; }
    if (w.id !== tpl) errs.push(`${grp.actor}: expected solo ${tpl}, got ${w.id}`);
    else if (branch && w.resolution.branchLabel !== branch) errs.push(`${grp.actor}: ${tpl} branch "${w.resolution.branchLabel}" ≠ "${branch}"`);
  };
  expectWinner(g.victor, 'HIDE', 'Go dark and reduce signal exposure');
  expectWinner(g.asmodeus, 'HIDE', 'Harden or sanitize a safehouse');
  expectWinner(g.celia, 'HIDE', 'Go dark and reduce signal exposure');
  expectWinner(g.juno, 'MOURN_LOSS', 'Visit the place of remembrance');
  expectWinner(g.talon, 'EVADE_PURSUERS', 'Go to ground in flooded tunnels');
  if (g.lansky.solo.winner) errs.push('lansky: expected coverage gap, got ' + g.lansky.solo.winner.id);
  if (!g.lansky.gap) errs.push('lansky: gap flag not set');
  const vc = g.victor.pairs.find((p) => p.target === 'celia');
  if (!vc || !vc.winner || vc.winner.id !== 'CULTIVATE_INFORMANT') errs.push('victor→celia: expected CULTIVATE_INFORMANT, got ' + (vc && vc.winner ? vc.winner.id : 'none'));
  if (vc && vc.winner && vc.winner.resolution.branchLabel !== 'Press for material intel when trust is sufficient') errs.push('victor→celia branch: ' + (vc.winner.resolution || {}).branchLabel);
  const vcSurveil = vc && vc.rows.find((x) => x.id === 'SURVEIL');
  if (!vcSurveil || vcSurveil.status !== 'shadowed') errs.push('victor→celia SURVEIL should be shadowed (50 vs 48), is ' + (vcSurveil && vcSurveil.status));
  const vcTend = vc && vc.rows.find((x) => x.id === 'TEND_WOUNDED');
  if (!vcTend || vcTend.status !== 'gate_failed') errs.push('victor→celia TEND_WOUNDED should gate-fail on cooldown, is ' + (vcTend && vcTend.status));
  const vt = g.victor.pairs.find((p) => p.target === 'talon');
  if (!vt || !vt.winner || vt.winner.id !== 'SURVEIL') errs.push('victor→talon: expected SURVEIL, got ' + (vt && vt.winner ? vt.winner.id : 'none'));
  const cv = g.celia.pairs.find((p) => p.target === 'victor');
  if (!cv || !cv.winner || cv.winner.id !== 'CONSULT_RIVAL') errs.push('celia→victor: expected CONSULT_RIVAL, got ' + (cv && cv.winner ? cv.winner.id : 'none'));
  const at = g.asmodeus.pairs.find((p) => p.target === 'talon');
  if (!at || !at.winner || at.winner.id !== 'PROTECT_KIN') errs.push('asmodeus→talon: expected PROTECT_KIN, got ' + (at && at.winner ? at.winner.id : 'none'));
  const jt = g.juno.pairs.find((p) => p.target === 'talon');
  if (!jt || !jt.winner || jt.winner.id !== 'PROTECT_KIN') errs.push('juno→talon: expected PROTECT_KIN, got ' + (jt && jt.winner ? jt.winner.id : 'none'));
  if (jt && jt.winner && jt.winner.resolution.branchLabel !== 'Travel toward the target\u2019s last known location') errs.push('juno→talon branch: ' + jt.winner.resolution.branchLabel);
  const jw = jt && jt.rows.find((x) => x.id === 'WARN_ALLY');
  if (!jw || jw.status !== 'shadowed') errs.push('juno→talon WARN_ALLY should be shadowed, is ' + (jw && jw.status));
  const mournTie = g.juno.solo.rows.find((x) => x.id === 'MOURN_LOSS');
  if (!mournTie || !mournTie.tie || !mournTie.tie.includes('SLEEP')) errs.push('juno MOURN_LOSS should tie with SLEEP');
  const celiaSleep = g.celia.solo.rows.find((x) => x.id === 'SLEEP');
  if (!celiaSleep || celiaSleep.status !== 'shadowed' || celiaSleep.resolution.magnitude !== 0.74) errs.push('celia SLEEP should be shadowed at mag 0.74');
  const asmSocial = g.asmodeus.solo.rows.find((x) => x.id === 'INTIMACY');
  if (!asmSocial || asmSocial.status !== 'gate_failed') errs.push('asmodeus INTIMACY should gate-fail (suppressor)');
  const press = {};
  for (const grp of r.groups) for (const p of grp.pressures) press[grp.actor + '→' + p.target] = p.winner.id + '/' + p.winner.resolution.magnitude;
  if (press['asmodeus→alex'] !== 'EXTRACT_VENGEANCE/0.34') errs.push('asmodeus→alex pressure: ' + press['asmodeus→alex']);
  if (press['victor→alex'] !== 'SURVEIL/0.48') errs.push('victor→alex pressure: ' + press['victor→alex']);
  if (press['celia→alex'] !== 'SURVEIL/0.44') errs.push('celia→alex pressure: ' + press['celia→alex']);
  if (press['lansky→alex']) errs.push('lansky→alex should emit no pressure (cooldown)');
  if (!r.needPressures.find((p) => p.target === 'pete' && p.need === 'thirst' && p.magnitude === 0.55)) errs.push('pete thirst need-pressure missing');
  const recip = reciprocalPairs(r);
  if (!recip.find((x) => (x.a === 'celia' && x.b === 'victor') || (x.a === 'victor' && x.b === 'celia'))) errs.push('victor↔celia reciprocal pair missing');
  // what-if: clearing the hunting pair tag flips Talon to SLEEP (safe lodgings)
  const s2 = applyOverrides(baseWorldState(), [{ kind: 'pairTag', from: 'victor', to: 'talon', tag: 'hunting', on: false }], 108);
  const r2 = resolveTick(s2);
  const t2 = r2.groups.find((x) => x.actor === 'talon');
  if (!t2.solo.winner || t2.solo.winner.id !== 'SLEEP') errs.push('what-if: talon expected SLEEP, got ' + (t2.solo.winner ? t2.solo.winner.id : 'none'));
  return errs;
}
