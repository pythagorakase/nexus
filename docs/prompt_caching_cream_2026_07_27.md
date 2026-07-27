# Prompt Caching and the Two-Pass Pipeline (C.R.E.A.M. Report)

**Date:** 2026-07-27 (v2, incorporating the Sol consult's corrections)
**Question (owner):** In configurations where Skald and Gaia call the same
model, can we exploit prompt caching? Would caching prevent placing the
differential (per-seat) prompts at the beginning?

## Verdict

**Caching does not constrain prompt design in our architecture.** The
per-seat differential material can open each system prompt — persona first —
at zero cache cost, because the thing that would have to match for
cross-seat cache sharing (the structured-output schema) already differs
between the two passes at serialization position zero on the transport that
matters.

Cross-seat caching within a turn is structurally unavailable on OpenAI,
moot in the pinned production configuration on Anthropic, and mechanically
possible only on the local transport (where it is not the pinned
architecture). Per-seat savings across turns and retries are real but
**not automatic in our current code**: neither transport's structured path
sends any cache directives today. Pocketing them is a small follow-up PR;
none of it cares where the differential prompt text sits.

## The Decisive Mechanic (OpenAI)

With structured outputs, OpenAI serializes the JSON schema **as a prefix to
the system message** for caching purposes. Writer and Gaia use different
schemas by design (`SkaldWriterWire`, 5,464 bytes serialized, vs
`SkaldGaiaWire`, 13,865 bytes — they diverge in the schema name after 14
characters, far below the 1,024-token caching minimum). The two calls
therefore fork at the first token, and no ordering of the prompt *text* can
recover a shared prefix. Cross-seat CREAM on OpenAI would require identical
schemas or abandoning structured output — both defeat the casting
architecture. Dead on arrival, and therefore free to ignore when designing
prompts.

## What Per-Seat Caching Actually Requires

- **OpenAI (gpt-5.6 family).** Supports implicit and explicit breakpoints;
  writes bill at 1.25×, reads at ~0.1×, prefix retention ≥ 30 minutes —
  play cadence fits. Two corrections to the lazy reading of "automatic":
  `prompt_cache_key` is required for the reliable gpt-5.6 matching path,
  and the implicit breakpoint lands on the *latest message*, which changes
  every request — so the reusable `[schema][system + setting]` boundary
  should be pinned with an explicit breakpoint, not assumed. Because
  writes are billable, implicit caching that never hits costs 25% extra;
  any implementation should watch `cache_write_tokens` vs `cached_tokens`.
  Our structured request builder currently forwards no cache key and no
  cache options (the unstructured path supports a key; the structured one
  does not expose it).
- **Retries.** Repair feedback is appended inside one scalar user-message
  string, so a retry's prefix *should* match through the original turn —
  but with no explicit breakpoint there, the hit is not guaranteed and
  has not been measured. The guaranteed design: explicit breakpoint after
  the stable system block, and (if repair caching matters) the original
  turn and the repair feedback as separate content blocks.
- **Anthropic (Opus 5 / Fable as rotating writers).** Current docs offer
  both top-level automatic caching and explicit block breakpoints; the
  operative fact is narrower: our structured path
  (`get_structured_completion`, the only path the pipeline uses) sends
  neither, so an Anthropic writer pays full input every turn. The
  `enable_cache` machinery in `scripts/api_anthropic.py` hangs off the
  legacy plain-completion path — dead code for turns. Prefix hierarchy is
  tools → system → messages; reads 0.1×, writes 1.25× (5-min TTL, free
  refresh on hit) or 2× (1-hour). The 1-hour TTL beats uncached cost at
  three calls inside the hour (one write + two reads; a repair retry
  counts as a read). Minimum cacheable prefix on Opus 5 / Fable 5 is 512
  tokens — `storyteller_core.md` alone clears it several times over.
- **Cross-seat on Anthropic** is moot in the pinned configuration
  (`gaia_model` pins Gaia to OpenAI). If `gaia_model` were unset behind an
  Anthropic writer, Gaia may follow on Anthropic via prompted or
  tool-envelope transport — and still would not share much: the writer's
  native `output_config.format` differs from Gaia's transport, and
  changing `output_config.format` invalidates the cache.
- **Local (llama-server)** applies the JSON-schema grammar at *decode
  time* — the schema never enters the prompt. This is the one transport
  where cross-seat prefix sharing is mechanically possible:
  `_format_gaia_user_prompt` already appends the finished scene at the
  tail of the shared `turn_prompt`. What breaks it is the per-seat system
  prompt at position zero. If a fully-local two-pass ever becomes a real
  configuration, the cache-optimal shape is a shared system prompt with
  the seat differential at the tail of the user message — the only place
  in the fleet where the owner's ordering question has a real cost.
  Recorded for the day it matters.
- **OpenRouter** forwards to heterogeneous upstreams; several (Moonshot,
  DeepSeek) run their own context caches and pass discounts through.
  Opportunistic; nothing to build.

## Answer to the Ordering Question

Persona-first differential prompts are free everywhere that matters. On
OpenAI the schemas fork the prefix before any prompt text is read; on
Anthropic the pinned configuration never pairs the two seats; only the
local transport would ever trade persona placement against cache, and it
is not the pinned configuration. Design the prompts for the models, not
the cache.

## Recommended Actions

1. **Do not contort the turn context** (intertitle position, warm-slice
   ordering) for cache prefix stability — the churn is the content.
2. **Follow-up PR (small, both transports):** wire explicit cache
   directives into the structured paths — an Anthropic system-block
   `cache_control` breakpoint (1-hour TTL as a config knob), and OpenAI
   `prompt_cache_key` per seat plus an explicit breakpoint after the
   system block, forwarded through the structured request builder. Log
   `cache_write_tokens` / `cached_tokens` (OpenAI) and
   `cache_creation_input_tokens` / `cache_read_input_tokens` (Anthropic)
   so the hit rate is measured, not assumed. Dollar impact is cents per
   turn; the realer win is time-to-first-token on 25K+-token prompts.
