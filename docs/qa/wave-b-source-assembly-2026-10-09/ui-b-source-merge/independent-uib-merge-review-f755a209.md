# UI-B merge: independent source review

Reviewed immutable merge `f755a209b64cd67f8feaaa774dbcd0679863452b`, tree
`6571e0ea7100ced95c1c7eb71939b2a1541a05a8`, against first parent `894d8c88`
and incoming `9e61307194699f202ad226d1b3af6e1b9350c2cd`. Their common ancestor
is 784 checkpoint `bf053542a1007b7fea768c13a06b768136df4aa8`. No product,
reference, shared state or existing 894 evidence was edited. This is source
review, not import, collection, behavioral test or final UI acceptance.

No production merge blocker found. The five UI-B product files exactly match
the reviewed incoming source. Of 44 changed runtime/test/config/UI paths,
38 exactly match that input. The six combined paths retain both sides:

- `narrative.py` adds only the UI-config router import/registration to the prior
  assembly; 812 boot admission and all prior turn/setup behavior remain intact.
- `settings_models.py` adds only required strict announcer timing and its UI
  field. Existing typed settings, reader bounds, CLI timeout and model contracts
  are unchanged. `nexus.toml` adds only the announcer's configured 5000ms value.
- `route_capabilities.py` adds only the player UI-config route; earlier player
  chunk range, operator transport and setup classifications remain present.
- Reachability baseline adds only `nexus/api/ui_config_endpoints.py`, which the
  new narrative import connects to the production graph.
- The Backstage test is incoming UI-B plus 840's authored, explicit Rootline
  coordinates. It retains 784 attention cases, the real TEST configuration before
  provider startup, precise missing-clock rollback, all four mandatory UI-B
  tests and full accepted/pending schema-3 parity.

Another 198 runtime/test/script/migration/config/prompt paths changed by the
previous assembly are byte-identical to first parent. This includes the prior
815/812 work, 811 module moves and migration149/150/151; it is preservation
evidence, not renewed behavioral proof of each lane. The incoming 777 shell,
announcer, map context and UI-config endpoint are its original149704 source.
UI-B preserves 784 attention/dimming; 778 VM and S6 pipeline UI remain unchanged
from the earlier assembly. Final777 capture changes and WaveA809/824 are still
absent and must merge normally before final UI/type/receipt acceptance.

The authorized static AST reachability tool was source-inspected and run with
the shared interpreter, `-I -S`, nice15 and load admission. Its only subprocess
inventory is Git; it does not import NEXUS. It reported406 maintained modules,
225 production-reachable, no baseline/classification/dependency/import findings,
and explicitly `route_reachability: not_proven`. Exact command, hash and output
are in `independent-uib-reachability-command-f755a209.json`, the matching `.txt`
and graph `.json`. HEAD and tracked/untracked status were clean before/after.
No pytest, application import, database read, UI process or heavy gate ran.

## Canonical source closure

The freshly derived declared closure is
`independent-uib-closure-f755a209.json`:24 documents against main `f073b371`,
including ten affected by this incremental merge. Read all ten bodies and the
actual source deltas: AGENTS, turn flow, decisions0008,0009,0010,0024,0034,0051,
0052 and0054. Their ruling/status/quotation bodies are unchanged. No new source
delta contradicts them: announcer timing introduces no prices, seat/model or
correspondence policy; router registration changes no turn lifecycle; map view
state relocation changes no scene-trail rule; clock formatting/history and time
lens behavior are retained; the narrow rail remains below the content.

0054 retains the union of NexusLayout, CSS and useNarrowShell sources, and its
bottom-rail ruling remains applicable alongside UI-B's additive section styles.
AGENTS/turn-flow and the five already-current incremental decision stamps are
`f073b371`; source semantics were re-read here, without claiming a future main.
The three newly affected 777 decisions0008,0051 and0052 still carry `4ae8b8d2`.
Their bodies are clear, but **those three stamps require the coordinator's normal
freshness update to the actual merge base before admission**. No stamp was edited
in this review. The other14 closure bodies/sources are unchanged by this merge
and retain the earlier independent review; that does not replace rechecking
closure after final predecessors. This24-document source inventory supersedes
the old21-document inventory for current source selection, not its historical
evidence. Final freshness tests and all runtime proof remain pending.

Codex — GPT-6
