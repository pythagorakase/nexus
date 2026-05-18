# Retrieval Query Strategy Bake-Off, 2026-05-18

## Summary

This diagnostic run compared three next-turn retrieval query sources:

- `raw_chunk`: the full source chunk text as one MEMNON query.
- `skald_directives`: Storyteller-style authorial retrieval directives.
- `local_llm`: locally generated retrieval queries from warm analysis.

The strongest result is that full raw chunk text should be the first-line
retrieval baseline. It was faster and clearly stronger on future-oracle metrics
than either smart-query path in this run. Skald/local queries still look useful
as targeted augmenters, especially for entity continuity in newer stories, but
the data does not support treating local LLM query generation as the primary
retrieval pillar.

## Method

The harness sampled 16 committed source-to-target chunk pairs:

- Slot 5: 8 new-story samples.
- Slot 2: 8 mature-story samples.

For each source chunk `n`, the scorer treated chunk `n + 1` as the held-out
future target and used two automatic judges:

- Future-oracle grades: query MEMNON with the actual target chunk text and use
  the top prior chunks as a relevance pool.
- Entity-continuity grades: prior chunks sharing the target chunk's character,
  place, or faction references.

The run also executed all 21 labeled golden queries from `ir_eval/ir_eval.db`
against the legacy `NEXUS` database as a separate MEMNON sanity check because
the existing qrels target that corpus. Golden queries are not a fourth strategy;
they validate that the underlying retrieval stack is not obviously broken during
the bake-off.

Most historical chunks did not have stored authorial directives, so
`skald_directives` used structured OpenAI backfills cached under
`temp/retrieval_bakeoff/overnight_cache.json`. That makes this a strong proxy
for Skald-style queries, not a perfect measurement of live stored directives.

## Results

| Strategy | Oracle Recall@10 | Oracle NDCG@10 | Oracle MRR | Entity Precision@10 | Entity NDCG@10 | Mean Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw_chunk` | 0.5563 | 0.5840 | 0.9688 | 0.3500 | 0.3445 | 6.58 |
| `skald_directives` | 0.3750 | 0.3110 | 0.4693 | 0.4125 | 0.4318 | 21.18 |
| `local_llm` | 0.2938 | 0.2624 | 0.4104 | 0.4750 | 0.3467 | 14.90 |

95 percent bootstrap intervals:

- Raw oracle NDCG: 0.4904 to 0.6684.
- Skald oracle NDCG: 0.2009 to 0.4303.
- Local oracle NDCG: 0.1345 to 0.4057.
- Raw oracle MRR: 0.9062 to 1.0000.
- Skald oracle MRR: 0.3049 to 0.6354.
- Local oracle MRR: 0.2125 to 0.6188.

Golden query sanity check over 21 labeled IR queries:

- P@5: 0.4667, 95 percent CI 0.3619 to 0.5619.
- P@10: 0.3381, 95 percent CI 0.2476 to 0.4381.
- MRR: 0.8889, 95 percent CI 0.7857 to 0.9762.
- NDCG@10: 0.5102, 95 percent CI 0.4051 to 0.6208.

## Slot Split

Slot 5 was mixed:

- Raw oracle NDCG: 0.5194.
- Skald oracle NDCG: 0.4650.
- Local oracle NDCG: 0.4958.
- Skald had the best entity NDCG at 0.5495.

Slot 2 was not mixed:

- Raw oracle NDCG: 0.6486.
- Skald oracle NDCG: 0.1571.
- Local oracle NDCG: 0.0290.

This suggests raw text is especially valuable for mature, dense corpora, while
targeted directives can still add useful continuity coverage in newer stories.

## Recommendation

Use full raw parent/current chunk text as the default first retrieval query.
Then spend the remaining query budget on targeted Storyteller directives.
Treat local LLM generated queries as an optional fallback or gap-filler rather
than a primary dependency.

The next production change should be narrow:

- Insert a `raw_chunk` retrieval query at the start of LORE deep queries when a
  current/parent chunk text is available.
- Keep `authorial_directives` after the raw query, up to the configured
  `lore.retrieval.max_deep_queries` budget.
- Use local LLM queries only for unfilled query slots.

That preserves the useful targeted-query path while removing the system's
dependence on a brittle local inference step that frequently fell back or
padded queries during this run.
