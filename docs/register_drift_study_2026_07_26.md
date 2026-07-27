# Register-Drift Study: LLM-Grown vs Human-Played Narrative

Generated at `2026-07-27T04:40:51+00:00` from read-only PostgreSQL sessions.

## Question

The study contrasts two measurable predictions. H1 (missing reader context) permits a high register intercept but predicts broadly flat register metrics across slot 5. H2 (two-LLM amplification) predicts rising slot-5 metrics that exceed trends in the human-in-the-loop slot-1 control.

## Corpus and prose sources

| Slot | Total rows | Playable | Analyzed | storyteller_text | raw_text | With presented choices |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 1425 | 1425 | 0 | 1425 | 0 |
| 5 | 111 | 110 | 110 | 110 | 0 | 110 |

Rows are ordered by playable ordinal, not raw chunk ID. For each row, `storyteller_text` is authoritative when non-empty; otherwise the analysis uses `raw_text`. Slot 1 therefore contributes legacy `raw_text` throughout, while slot 5 contributes `storyteller_text` throughout. The canonical `nexus.agents.orrery.reconstruction.playable_narrative_predicate` excludes non-playable rows, and rows with neither prose source are excluded.

## Methods

All database connections use `psycopg2`, call `set_session(readonly=True)` before any query, and verify `transaction_read_only=on`. The script issues only `SHOW` and `SELECT` statements.

Words are lowercase Unicode alphabetic runs; punctuation is treated as a boundary. Content-word sets remove this fixed built-in stopword list: a, an, and, are, as, at, be, been, being, but, by, can, could, did, do, does, for, from, had, has, have, he, her, hers, him, his, i, if, in, into, is, it, its, may, me, might, my, not, of, on, or, our, ours, she, should, so, than, that, the, their, theirs, them, then, there, these, they, this, those, to, too, was, we, were, what, when, where, which, who, whom, why, will, with, would, you, your, yours.

1. **Lexical novelty rate.** For each chunk, the fraction of its content-word types not present in any earlier chunk in that slot. The running vocabulary is updated only after scoring the chunk; an empty content-word set scores 0.
2. **Coinage density.** Count per 1,000 words of maximal spans with two or more consecutive title-cased alphabetic tokens separated by whitespace. The first token after the start of text or `.`, `!`, or `?`, or a newline cannot begin a span, excluding sentence-initial capitalization.
3. **Console/proclamation register.** Per-chunk count of lines with at least eight alphabetic characters for which at least 60% of those characters are uppercase.
4. **Ceremonial-syntax density.** Per 1,000 words, the sum of non-empty alphabetic lines ending in a colon, U+2014 em dashes, and matches in this fixed generic ritual/formality lexicon: bind, binding, bindings, binds, bound, covenant, covenanted, covenanting, covenants, custodial, custodian, custodians, custodianship, oath, oaths, protocol, protocols, record, recorded, recording, records, rite, rites, sanction, sanctioned, sanctioning, sanctions, seal, sealed, sealing, seals, witness, witnessed, witnesses, witnessing.
5. **Choice-list self-similarity.** Mean pairwise Jaccard similarity of the presented choices' content-word sets; undefined with fewer than two choices. Two empty sets are assigned 0.
6. **Choice-topic recurrence.** Jaccard similarity of the current turn's pooled presented-choice content words against the union from choice-bearing chunks among the preceding five playable turns. It is undefined when none of those turns has choices.
7. **Mean sentence length.** Mean alphabetic-word count in non-empty segments split at `.`, `!`, `?`, or a newline.
8. **Dialogue-line fraction.** Fraction of non-empty lines containing a straight or curly double quote.
9. **Second-person pronoun rate.** Per 1,000 words, matches of `you`, `your`, `yours`, `yourself`, and `yourselves`.

Per-chunk values are averaged into consecutive, non-overlapping 10-chunk windows; a final partial window is retained. For each slot and metric, the reported ordinary least-squares slope is fit inline to window mean versus the window's mean playable ordinal, so its unit is metric units per chunk. Position-normalized early, middle, and late means use inclusive 0–10%, 45–55%, and 90–100% playable-ordinal percentile bands. Missing metric values are omitted from means, never replaced with zero.

A metric contributes to a slot's drift velocity when its OLS slope is positive and its late-band mean exceeds its early-band mean by more than 20% relative. A zero or missing early mean has undefined relative change and is conservatively not counted.

## Metric tables

### Lexical novelty rate

Fraction of the chunk's content-word types absent from all earlier chunks in the same slot.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 0.210 | 0.032 | 0.027 | -8.89407e-05 | 0.634 | 0.024 |
| 5 | 110 | 0.438 | 0.076 | 0.051 | -0.00262679 | 0.458 | 0.049 |

### Coinage density

Title-Case multiword spans beginning mid-sentence per 1,000 words.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 5.019 | 5.666 | 6.136 | 0.000109946 | 9.543 | 11.458 |
| 5 | 110 | 6.512 | 3.565 | 2.081 | -0.0400137 | 6.237 | 2.289 |

### Console/proclamation register

Count of ALL-CAPS-dominant lines in the chunk.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 3.692 | 0.105 | 0.035 | -0.00344116 | 0.000 | 0.000 |
| 5 | 110 | 1.909 | 1.400 | 3.727 | 0.0145455 | 2.000 | 3.900 |

### Ceremonial-syntax density

Colon-terminated lines, em dashes, and formality-lexicon matches per 1,000 words.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 15.090 | 22.238 | 19.759 | 0.000143538 | 14.062 | 19.441 |
| 5 | 110 | 9.044 | 7.077 | 10.782 | 0.0303639 | 8.595 | 10.875 |

### Choice-list self-similarity

Mean pairwise content-word Jaccard similarity among presented choices.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| 5 | 110 | 0.041 | 0.037 | 0.037 | -0.0001026 | 0.043 | 0.034 |

### Choice-topic recurrence

Content-word Jaccard similarity against choices in the preceding five playable turns.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| 5 | 109 | 0.127 | 0.104 | 0.121 | -4.35201e-05 | 0.123 | 0.124 |

### Mean sentence length

Mean alphabetic-word count per non-empty sentence or line segment.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 7.479 | 5.785 | 6.775 | -0.000824997 | 8.729 | 6.846 |
| 5 | 110 | 10.187 | 9.936 | 9.012 | -0.0028307 | 10.257 | 8.931 |

### Dialogue-line fraction

Fraction of non-empty lines containing a straight or curly double-quote character.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 0.152 | 0.162 | 0.179 | -3.80626e-05 | 0.062 | 0.174 |
| 5 | 110 | 0.266 | 0.361 | 0.332 | -0.000189529 | 0.243 | 0.323 |

### Second-person pronoun rate

Second-person pronoun tokens per 1,000 words.

| Slot | Observations | Early 0–10% | Middle 45–55% | Late 90–100% | OLS slope/chunk | First 10-chunk window | Last 10-chunk window |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 40.779 | 56.488 | 14.126 | -0.00442029 | 67.901 | 13.674 |
| 5 | 110 | 32.775 | 6.377 | 7.715 | -0.220557 | 32.420 | 7.338 |

## Verdict

Here, “exceeds” means that the slot-5 OLS slope is numerically greater than the slot-1 OLS slope for the same metric. Choice metrics are explicitly within-slot only because slot 1 has no `choice_object.presented` data.

| Metric | Slot 1 slope | Slot 5 slope | Slot-5 trend exceeds slot 1? |
| --- | ---: | ---: | :--- |
| Lexical novelty rate | -8.89407e-05 | -0.00262679 | no |
| Coinage density | 0.000109946 | -0.0400137 | no |
| Console/proclamation register | -0.00344116 | 0.0145455 | yes |
| Ceremonial-syntax density | 0.000143538 | 0.0303639 | yes |
| Choice-list self-similarity | n/a | -0.0001026 | no control |
| Choice-topic recurrence | n/a | -4.35201e-05 | no control |
| Mean sentence length | -0.000824997 | -0.0028307 | no |
| Dialogue-line fraction | -3.80626e-05 | -0.000189529 | no |
| Second-person pronoun rate | -0.00442029 | -0.220557 | no |

**Slot 1 drift velocity:** 2 metric(s) (of 7 measurable).

**Slot 5 drift velocity:** 1 metric(s) (of 9 measurable).

Across the seven controlled prose/style metrics, slot 5 has the greater OLS slope on 2. This is a directional comparison of the registered measurements, not a causal identification result; the individual slopes and band movements above determine whether the evidence looks more like a flat high-intercept register (H1) or escalating register (H2).

Overall verdict: the measured pattern does not show broad H2-style escalation. Slot 5 has the greater slope on only 2 of 7 controlled metrics, with drift velocity 1 versus 2 in slot 1. This leans toward H1's flat/high-intercept trend prediction, while the individual metrics marked “yes” remain localized H2-compatible signals; it does not establish missing context as the mechanism.

## Limitations

Slot 1 is not a model-pure control: it spans model heterogeneity, and its legacy `raw_text` interleaves human player lines with narration. The actual contrast is therefore human-in-the-loop versus LLM-in-the-loop, and the interleaving is part of the phenomenon rather than something filtered away. The hand-built stopword, formality, pronoun, capitalization, and segmentation rules introduce lexicon-choice and operationalization bias; other reasonable lists or tokenizers can move the estimates. Finally, a temporal trend or cross-slot slope difference does not prove the amplification mechanism: plot, character, prompt, model, and campaign-era differences remain plausible causes. The two choice metrics have no slot-1 control and support only within-slot trend statements.
