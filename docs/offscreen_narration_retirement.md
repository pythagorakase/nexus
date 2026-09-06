# Off-Screen Narration Retirement

Issue #846 retires the provider call that expanded a canonical Orrery resolution
into 80–180 words of off-screen prose. It preserves the deterministic resolution,
world events, promotion verdict, perceptual descriptor, and durable job fences.
Skald continues to author player-visible prose.

## Consumer Audit

The repository-wide `offscreen_narrations` trace found these consumers:

- `nexus/agents/orrery/bleed.py`: candidate selection used to load `text`, but
  `BleedCandidate.to_prompt_dict()` excluded it. Candidates now omit the unused
  field entirely. Sync and async uptake only used prose for a diagnostic
  four-gram overlap; the actual acceptance heuristic is still exact actor-name
  matching. The diagnostic now compares the offered descriptor, with a distinct
  `descriptor_four_gram_overlap_ratio` log field so old and new measurements
  cannot be confused.
- `nexus/agents/orrery/worker.py`: status reports count rows and embedding/job
  states; they never require the full prose. Those identifiers and counts remain
  compatible with the API and QA queue inspection.
- `nexus/agents/memnon/memnon.py`: read-only SQL allows access to off-screen rows
  for explicit audit queries, but warm-slice, text-search, and vector retrieval
  exclude them. `test_retrieval_boundaries.py` and `test_memnon_whitelist.py`
  continue to enforce those boundaries. Historical prose remains available
  through the same audited table; new canonical facts remain linked by
  resolution and tick IDs.
- Integration fixtures and historical milestone documents contain the remaining
  reads. No embedding processor or future retrieval implementation consumes the
  text. The design plan's old statement that MEMNON already queried both tables
  was inaccurate and is corrected.

A future off-screen retrieval feature can use canonical resolution briefs,
state changes, events, and perceptual descriptors. It must define its entitlement
and legacy-record handling before indexing. This change does not assume that
unwritten future consumers require generated prose, nor does it delete their
existing source material.

## Durable and Configuration Contracts

The historical `orrery_narration_jobs`, `narration_status`,
`offscreen_narrations`, worker entry-point names, and status counters remain.
New `text` values are deterministic JSON copies of the descriptor, marked by
`perceptual_descriptor.record_kind = "deterministic_descriptor"`. Existing prose
and descriptors are never rewritten. Missing markers mean legacy or unclassified
records, not a guarantee that the content was authored by a provider.

New jobs have no provider/model metadata. Old queued or expired jobs follow the
same lease, owner, nonce, anchor, uniqueness, and retry fences while producing
only descriptors; an active lease remains owned by its current worker. Existing
provider metadata and historical usage ledgers are preserved. The new path emits
no provider request or fabricated usage event. Experience rendering, maturation,
QA budget fences, and queue settlement checks retain their existing behavior.

`[orrery.narration]` now contains queue settings only. Removed `mode`, `provider`,
`model_ref`, `temperature`, and `max_output_tokens` settings fail validation if
left in an external runtime config. Regenerate derived QA configs from the
current `nexus.toml`. No schema migration or live-slot rewrite is needed.

## Validation and Remaining Scope

The PostgreSQL suite `test_narration_job_fencing_pg.py` uses disposable template
clones. It covers genuine resolve, commit, promotion, descriptor completion,
Bleed eligibility and uptake, expired-lease races, stale anchors, lock-wait
expiry, deduplication, legacy record retention, and zero provider usage.
Provider entry points are forbidden during the retirement integration case.
The existing worker, Bleed, MEMNON boundary, config, QA, and accepted-commit
regressions cover the supporting contracts.

Explicit return receipts remain in brainstorm cluster C054, "Give Consequential
Off-Screen Events a Return Contract." This retirement preserves the current
actor-name uptake heuristic and does not claim to deliver that separate contract.
