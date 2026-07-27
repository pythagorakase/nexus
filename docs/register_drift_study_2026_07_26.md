# Register-Drift Study: LLM-Grown vs Human-Played Narrative

Study date: **2026-07-27**. Generated at `2026-07-27T05:01:25+00:00` from read-only PostgreSQL sessions.

## Question

The study contrasts two measurable predictions. H1 (missing reader context) permits a high register intercept but predicts broadly flat register metrics across slot 5. H2 (two-LLM amplification) predicts rising slot-5 metrics that exceed trends in the slot-1 storyteller channel. The separately measured slot-1 player channel is an observational human-register series.

## Corpus and prose sources

| Slot | Total rows | Playable | Analyzed | storyteller_text | raw_text | Structured choice chunks |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1425 | 1425 | 1425 | 0 | 1425 | 0 |
| 5 | 111 | 110 | 110 | 110 | 0 | 110 |

| Series | Playable positions | Chunks with text | Choice/menu chunks | Choice coverage |
| --- | ---: | ---: | ---: | ---: |
| Slot 1 storyteller | 1425 | 1425 | 225 | 15.8% |
| Slot 1 player | 1425 | 1388 | 0 | 0.0% |
| Slot 5 | 110 | 110 | 110 | 100.0% |

Rows are ordered by playable ordinal, not raw chunk ID. For each row, `storyteller_text` is authoritative when non-empty; otherwise the analysis uses `raw_text`. The source census shows exactly how many chunks used each field in each slot. Slot 1's legacy `raw_text` is split at recurring `## Storyteller` and `## You` headings; text before the first heading belongs to the storyteller channel. The delimiter headings and `<!-- SCENE BREAK ... -->` comments are removed. Slot 5 uses its `storyteller_text` unchanged. The canonical `nexus.agents.orrery.reconstruction.playable_narrative_predicate` excludes non-playable rows, and rows with neither prose source are excluded.

Legacy recovery found menus in 225 of 1425 slot-1 chunks (15.8%). Because coverage is below 30%, both choice metrics are marked “partial control” in the verdict table.

## Methods

All database connections use `psycopg2`, call `set_session(readonly=True)` before any query, and verify `transaction_read_only=on`. The script issues only `SHOW` and `SELECT` statements.

The three prose series are slot 1 storyteller, slot 1 player, and slot 5. A missing channel in a playable chunk is omitted from metric means rather than scored as zero, while the chunk still retains its slot position. Running lexical vocabularies are independent for all three series.

Legacy slot-1 choices are recovered only from storyteller-channel lines matching the numbered-option pattern `^\s*(?:###\s*)?\*{0,2}\d+[.)]`. Items must form a sequential 1-based block of 2–6 options. Description lines may intervene, and when several blocks qualify, the final block is used. The two choice metrics remain undefined for the player channel.

Words are lowercase Unicode alphabetic runs; punctuation is treated as a boundary. Content-word sets remove this fixed built-in stopword list: a, an, and, are, as, at, be, been, being, but, by, can, could, did, do, does, for, from, had, has, have, he, her, hers, him, his, i, if, in, into, is, it, its, may, me, might, my, not, of, on, or, our, ours, she, should, so, than, that, the, their, theirs, them, then, there, these, they, this, those, to, too, was, we, were, what, when, where, which, who, whom, why, will, with, would, you, your, yours.

1. **Lexical novelty rate.** For each chunk, the fraction of its content-word types not present in any earlier chunk in the same series. The running vocabulary is updated only after scoring the chunk; an empty content-word set scores 0.
2. **Coinage density.** Count per 1,000 words of maximal spans with two or more consecutive title-cased alphabetic tokens separated by whitespace. The first token after the start of text or `.`, `!`, or `?`, or a newline cannot begin a span, excluding sentence-initial capitalization.
3. **Console/proclamation register.** Per 1,000 words, lines with at least eight alphabetic characters for which at least 60% of those characters are uppercase. Only alphabetic characters enter the case ratio.
4. **Ceremonial-syntax density.** Per 1,000 words, the sum of non-empty alphabetic lines ending in a colon, U+2014 em dashes, and matches in this fixed generic ritual/formality lexicon: bind, binding, bindings, binds, bound, covenant, covenanted, covenanting, covenants, custodial, custodian, custodians, custodianship, oath, oaths, protocol, protocols, record, recorded, recording, records, rite, rites, sanction, sanctioned, sanctioning, sanctions, seal, sealed, sealing, seals, witness, witnessed, witnesses, witnessing.
5. **Choice-list self-similarity.** Mean pairwise Jaccard similarity of the presented or recovered choices' content-word sets; undefined with fewer than two choices. Two empty sets are assigned 0.
6. **Choice-topic recurrence.** Jaccard similarity of the current turn's pooled choice content words against the union from choice-bearing chunks among the preceding five playable turns. It is undefined when none of those turns has choices.
7. **Mean sentence length.** Mean alphabetic-word count in non-empty segments split at `.`, `!`, `?`, or a newline.
8. **Dialogue-line fraction.** Fraction of non-empty lines containing a straight or curly double quote.
9. **Second-person pronoun rate.** Per 1,000 words, matches of `you`, `your`, `yours`, `yourself`, and `yourselves`.

Per-chunk values are averaged into consecutive, non-overlapping 10-chunk windows; a final partial window is retained. For each series and metric, ordinary least squares is fit inline to window mean versus the window's mean campaign position, where each chunk position is its playable ordinal divided by the maximum playable ordinal in that series. The x axis is therefore normalized to (0, 1], and the slope unit is metric units per campaign. Each slope's standard error uses the inline OLS residual estimate `sqrt((SSE / (n - 2)) / Sxx)` and is undefined with fewer than three window points. Position-normalized early, middle, and late means use inclusive 0–10%, 45–55%, and 90–100% playable-position bands. Missing metric values are omitted from means, never replaced with zero.

For every slot-5 minus slot-1 storyteller slope difference, the two series' non-empty window points are pooled, labels are shuffled while preserving the original group sizes, and both slopes are refitted. The reported two-sided p-value uses 2,000 permutations, compares absolute slope differences, uses fixed random seed `20260726`, and applies the plus-one Monte Carlo correction. A numerically greater slot-5 slope is “yes” only when `p < 0.05`; otherwise it is “provisional (underpowered)”.

A metric contributes to a series' drift velocity when its OLS slope is positive and its late-band mean exceeds its early-band mean by more than 20% relative. A zero or missing early mean has undefined relative change and is conservatively not counted. The reported uncertainty-aware summary further requires that metric's cross-slot verdict to be a non-provisional “yes”; provisional, no, and insufficient comparisons are not counted.

## Metric tables

### Lexical novelty rate

Fraction of the chunk's content-word types absent from all earlier chunks in the same channel series.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 0.218 | 0.394 | 0.438 |
| Middle 45–55% | 0.034 | 0.160 | 0.076 |
| Late 90–100% | 0.024 | 0.131 | 0.051 |
| OLS slope/campaign | -0.135162 | -0.207172 | -0.288947 |
| OLS slope SE | 0.0183522 | 0.0281125 | 0.0884231 |
| First 10-chunk window | 0.656 | 0.593 | 0.458 |
| Last 10-chunk window | 0.025 | 0.102 | 0.049 |

### Coinage density

Title-Case multiword spans beginning mid-sentence per 1,000 words.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 5.510 | 0.968 | 6.512 |
| Middle 45–55% | 6.794 | 0.858 | 3.565 |
| Late 90–100% | 7.710 | 1.811 | 2.081 |
| OLS slope/campaign | 1.72294 | 1.83225 | -4.40151 |
| OLS slope SE | 1.35988 | 0.783743 | 1.17611 |
| First 10-chunk window | 10.122 | 0.000 | 6.237 |
| Last 10-chunk window | 14.032 | 0.000 | 2.289 |

### Console/proclamation register

ALL-CAPS-dominant lines per 1,000 words.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 12.476 | 0.000 | 1.360 |
| Middle 45–55% | 0.150 | 11.499 | 1.515 |
| Late 90–100% | 0.094 | 0.493 | 3.614 |
| OLS slope/campaign | -12.4543 | -4.74476 | 1.85015 |
| OLS slope SE | 2.01808 | 4.39465 | 1.28143 |
| First 10-chunk window | 0.000 | 0.000 | 1.425 |
| Last 10-chunk window | 0.000 | 0.000 | 3.811 |

### Ceremonial-syntax density

Colon-terminated lines, em dashes, and formality-lexicon matches per 1,000 words.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 16.644 | 0.834 | 9.044 |
| Middle 45–55% | 24.549 | 1.267 | 7.077 |
| Late 90–100% | 22.351 | 3.082 | 10.782 |
| OLS slope/campaign | 2.21131 | 2.37666 | 3.34003 |
| OLS slope SE | 1.65441 | 0.938353 | 1.75641 |
| First 10-chunk window | 15.742 | 0.000 | 8.595 |
| Last 10-chunk window | 23.253 | 0.000 | 10.875 |

### Choice-list self-similarity

Mean pairwise content-word Jaccard similarity among presented or recovered choices.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 225 | 0 | 110 |
| Early 0–10% | 0.024 | n/a | 0.041 |
| Middle 45–55% | n/a | n/a | 0.037 |
| Late 90–100% | 0.006 | n/a | 0.037 |
| OLS slope/campaign | -0.00895442 | n/a | -0.0112861 |
| OLS slope SE | 0.012729 | n/a | 0.00738243 |
| First 10-chunk window | 0.016 | n/a | 0.043 |
| Last 10-chunk window | n/a | n/a | 0.034 |

### Choice-topic recurrence

Content-word Jaccard similarity against presented or recovered choices in the preceding five playable turns.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 217 | 0 | 109 |
| Early 0–10% | 0.074 | n/a | 0.127 |
| Middle 45–55% | n/a | n/a | 0.104 |
| Late 90–100% | n/a | n/a | 0.121 |
| OLS slope/campaign | 0.092184 | n/a | -0.00478721 |
| OLS slope SE | 0.0248337 | n/a | 0.0144558 |
| First 10-chunk window | 0.050 | n/a | 0.123 |
| Last 10-chunk window | n/a | n/a | 0.124 |

### Mean sentence length

Mean alphabetic-word count per non-empty sentence or line segment.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 7.668 | 9.839 | 10.187 |
| Middle 45–55% | 5.635 | 8.548 | 9.936 |
| Late 90–100% | 6.784 | 9.410 | 9.012 |
| OLS slope/campaign | -1.39164 | 0.693939 | -0.311377 |
| OLS slope SE | 0.339136 | 0.894736 | 0.450068 |
| First 10-chunk window | 9.843 | 4.817 | 10.257 |
| Last 10-chunk window | 6.741 | 16.042 | 8.931 |

### Dialogue-line fraction

Fraction of non-empty lines containing a straight or curly double-quote character.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 0.174 | 0.043 | 0.266 |
| Middle 45–55% | 0.162 | 0.568 | 0.361 |
| Late 90–100% | 0.180 | 0.687 | 0.332 |
| OLS slope/campaign | -0.094928 | 0.779413 | -0.0208482 |
| OLS slope SE | 0.0257846 | 0.0641492 | 0.0601336 |
| First 10-chunk window | 0.080 | 0.000 | 0.243 |
| Last 10-chunk window | 0.173 | 0.750 | 0.323 |

### Second-person pronoun rate

Second-person pronoun tokens per 1,000 words.

| Statistic | Slot 1 storyteller | Slot 1 player | Slot 5 |
| :--- | ---: | ---: | ---: |
| Observations | 1425 | 1388 | 110 |
| Early 0–10% | 41.501 | 1.683 | 32.775 |
| Middle 45–55% | 58.098 | 18.931 | 6.377 |
| Late 90–100% | 9.240 | 22.455 | 7.715 |
| OLS slope/campaign | -10.8297 | 22.2952 | -24.2612 |
| OLS slope SE | 6.22895 | 3.57929 | 6.1014 |
| First 10-chunk window | 68.436 | 4.762 | 32.420 |
| Last 10-chunk window | 10.795 | 6.250 | 7.338 |

## Human-dampener contrast

Each value below is the slot-1 storyteller band mean minus the slot-1 player band mean; a positive value means the storyteller channel is higher on that metric.

| Metric | Early 0–10% gap | Middle 45–55% gap | Late 90–100% gap |
| --- | ---: | ---: | ---: |
| Lexical novelty rate | -0.175 | -0.126 | -0.107 |
| Coinage density | +4.542 | +5.936 | +5.899 |
| Console/proclamation register | +12.476 | -11.349 | -0.398 |
| Ceremonial-syntax density | +15.811 | +23.282 | +19.269 |
| Mean sentence length | -2.171 | -2.913 | -2.625 |
| Dialogue-line fraction | +0.131 | -0.406 | -0.507 |
| Second-person pronoun rate | +39.818 | +39.167 | -13.214 |

The storyteller-minus-player gap is positive for 5 of 7 prose metrics early, 3 of 7 in the middle, and 2 of 7 late. This describes channel separation at comparable campaign positions; gap magnitudes are not comparable across metrics because their units differ. It does not show that a human utterance caused the next storyteller response to dampen, and it is not a causal estimate.

## Verdict

The slope difference is slot 5 minus slot-1 storyteller in metric units per campaign. “Yes” means that difference is positive and its two-sided permutation p-value is below 0.05; a positive difference at p ≥ 0.05 is “provisional (underpowered)”. The storyteller channel is the model-output control; the player channel remains observational. Choice comparisons use only the sparse structurally recovered slot-1 menus and are labeled by their coverage.

| Metric | Slot 1 slope/campaign | Slot 1 SE | Slot 5 slope/campaign | Slot 5 SE | Difference | Permutation p | Control basis | Slot-5 trend exceeds storyteller? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| Lexical novelty rate | -0.135162 | 0.0183522 | -0.288947 | 0.0884231 | -0.153785 | 0.134433 | full control | no |
| Coinage density | 1.72294 | 1.35988 | -4.40151 | 1.17611 | -6.12445 | 0.30085 | full control | no |
| Console/proclamation register | -12.4543 | 2.01808 | 1.85015 | 1.28143 | 14.3045 | 0.0689655 | full control | provisional (underpowered) |
| Ceremonial-syntax density | 2.21131 | 1.65441 | 3.34003 | 1.75641 | 1.12873 | 0.876062 | full control | provisional (underpowered) |
| Choice-list self-similarity | -0.00895442 | 0.012729 | -0.0112861 | 0.00738243 | -0.00233163 | 0.937031 | partial control | no |
| Choice-topic recurrence | 0.092184 | 0.0248337 | -0.00478721 | 0.0144558 | -0.0969712 | 0.01999 | partial control | no |
| Mean sentence length | -1.39164 | 0.339136 | -0.311377 | 0.450068 | 1.08026 | 0.510245 | full control | provisional (underpowered) |
| Dialogue-line fraction | -0.094928 | 0.0257846 | -0.0208482 | 0.0601336 | 0.0740798 | 0.497751 | full control | provisional (underpowered) |
| Second-person pronoun rate | -10.8297 | 6.22895 | -24.2612 | 6.1014 | -13.4316 | 0.49975 | full control | no |

**Slot 1 storyteller drift velocity:** 0 metric(s) (of 2 within-series candidate(s) and 9 measurable; provisional comparisons excluded).

**Slot 1 player drift velocity:** 0 metric(s) (of 4 within-series candidate(s) and 7 measurable; provisional comparisons excluded).

**Slot 5 drift velocity:** 0 metric(s) (of 1 within-series candidate(s) and 9 measurable; provisional comparisons excluded).

Across the seven fully controlled prose/style metrics, slot 5 has a non-provisional greater OLS slope on 0; 4 additional positive difference(s) are underpowered. This is an uncertainty-qualified comparison of the registered measurements, not a causal identification result; the individual slopes and band movements determine whether the evidence looks more like a flat high-intercept register (H1) or escalating register (H2).

Overall verdict: the measured prose pattern does not show broad H2-style escalation. Slot 5 has a significantly greater slope on only 0 of 7 fully controlled prose metrics; 4 additional comparison(s) are provisional. Uncertainty-filtered drift velocity is 0 versus 0 in the slot-1 storyteller series. This leans toward H1's flat/high-intercept trend prediction, while metrics marked “yes” remain localized H2-compatible signals; it does not establish missing context as the mechanism.

## Limitations

Slot 1 is not a model-pure control: it spans model heterogeneity, and the controlling storyteller channel was generated inside a human-in-the-loop campaign. The actual contrast is therefore human-in-the-loop versus LLM-in-the-loop, not one model versus another under purified conditions. Its legacy `raw_text` interleaves narration with human player lines; the structural split makes those channels separately observable, but the human input and its downstream influence are part of the phenomenon, not filtered away. The section parser depends on the legacy headings, and recovered numbered menus are a sparse heuristic sample that can include or miss list-like prose. The hand-built stopword, formality, pronoun, capitalization, and segmentation rules introduce lexicon-choice and operationalization bias; other reasonable lists or tokenizers can move the estimates. Slot 5 contributes 11 non-empty window points to every slope fit. That small slot-5 window count limits slope precision and the power of the permutation comparisons; the p-values quantify sampling extremeness under label exchangeability, not freedom from corpus dependence. Finally, a temporal trend, channel gap, or cross-slot slope difference does not prove the amplification or dampening mechanism: plot, character, prompt, model, and campaign-era differences remain plausible causes.
