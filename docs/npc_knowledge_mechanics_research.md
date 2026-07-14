# Per-NPC Knowledge, Claims, and Rumors: Mechanics Research

Related to GitHub issue #477.

## Purpose

Issue #477 exposes a broader modeling gap: NEXUS does not have a durable way to
represent what a particular NPC knows, believes, has heard, has forgotten, or is
willing to disclose.

This note surveys comparable game and research systems, with particular attention
to SkyrimNet and its companion project IntelEngine. It is an exploratory design
note, not an implementation specification.

## Executive summary

The strongest systems do not treat "knowledge" as a single collection of prompt
fragments. They distinguish at least five things:

1. **Canonical incident:** what actually happened in the world.
2. **Claim or account:** a communicable assertion about that incident, which may
   be incomplete, distorted, or false.
3. **NPC awareness:** the fact that a particular NPC possesses a particular
   claim, including how and when it was acquired.
4. **Recall and disclosure:** whether the NPC recalls the claim in the current
   context and whether they are willing to reveal it.
5. **Consequences:** suspicion, leverage, relationship changes, plans, dialogue
   options, and event gates derived from the claim.

This distinction matters because retrieval is not knowledge. A vector search can
choose which eligible memories to put in a prompt, but it cannot establish whether
an NPC was ever entitled to possess those memories.

For NEXUS, the most promising direction is a sparse, typed ledger of story-relevant
claims and per-NPC awareness records. It should not attempt a universal proposition
calculus, recursive theory of mind, or continuous numeric confidence for every fact.

## SkyrimNet

Repository inspected at commit
[`040fda1`](https://github.com/MinLL/SkyrimNet-GamePlugin/tree/040fda1d802d67d805f72be472b849d26f9b4d78).

### Private episodic memory

SkyrimNet gives each NPC private first-person memories synthesized from witnessed
or otherwise relevant recent events. A generated record contains content, location,
emotion, importance, tags, and a memory type. These memories are selected through
semantic recall, weighted by importance, and subject to decay.

Source: [memory-generation prompt and schema](https://github.com/MinLL/SkyrimNet-GamePlugin/blob/040fda1d802d67d805f72be472b849d26f9b4d78/SKSE/Plugins/SkyrimNet/prompts/memory/generate_memory.prompt#L24-L58).

This is useful as experiential memory, but its natural-language form makes exact
questions difficult to answer reliably: Does an NPC know a specific claim? Who told
them? Is it firsthand? Does another memory contradict it?

### Authored World Knowledge

World Knowledge entries contain authored content plus eligibility predicates such
as actor, faction, NPC group, quest stage, or race. Important entries can always be
injected; less important entries are semantically retrieved. Entries sharing a
`knowledge_key` can provide progressively more specific variants, with the
highest-priority applicable entry winning.

Sources:

- [knowledge-entry schema](https://github.com/MinLL/SkyrimNet-GamePlugin/blob/040fda1d802d67d805f72be472b849d26f9b4d78/SKSE/Plugins/SkyrimNet/prompts/agent_knowledge_builder.prompt#L16-L35)
- [condition examples](https://github.com/MinLL/SkyrimNet-GamePlugin/blob/040fda1d802d67d805f72be472b849d26f9b4d78/SKSE/Plugins/SkyrimNet/prompts/agent_knowledge_builder.prompt#L39-L80)

The important limitation is that this appears to be a prompt-eligibility system,
not a persistent epistemic ledger. Eligibility is recomputed from current
conditions; the system does not record that a particular NPC learned a particular
claim from a particular source. A poorly chosen transient condition, such as
location, could effectively cause an NPC to know and then unknow information as the
condition changes.

### What is worth borrowing

- Separate compact, always-present crucial knowledge from incidental knowledge
  selected through semantic retrieval.
- Preserve private first-person episodic memories as one source of claims.
- Allow specific authored knowledge to supersede general background knowledge.

These are presentation and retrieval mechanics. They still need an authoritative
awareness layer underneath them.

### Source-availability caveat

The repository is public and contains useful Papyrus scripts, prompts, and API
documentation, but it has no declared license and does not include the native core
implementation. One commit explicitly stopped tracking an auto-copied core header:
[commit `d80e365`](https://github.com/MinLL/SkyrimNet-GamePlugin/commit/d80e365dff3d43c6f9513a09407bfdefc440933f).
It is therefore safe to study as a design reference, but code reuse would require
license clarification or permission.

## IntelEngine: a concrete SkyrimNet gossip implementation

SkyrimNet's documentation points to
[IntelEngine](https://github.com/galanx/IntelEngine-GamePlugin), whose public scripts
contain a more directly relevant gossip implementation. The inspected commit was
[`a42311f`](https://github.com/galanx/IntelEngine-GamePlugin/tree/a42311f2f81e3776961f80fcf90396f064011955).

### Mechanics

- Each NPC retains bounded FIFO lists of facts, rumors heard, and rumors shared.
- Heard rumors record the text, immediate teller, and time.
- Shared rumors record the text, recipient, and time.
- An LLM chooses an initial piece of gossip from genuine memories while being shown
  a canonical `Knows` block intended to prevent contradictions.
- Off-screen simulation propagates the unchanged rumor string through a random
  chain of up to ten additional NPCs. Candidates are selected through existing
  social or shared-event relationships, and loops within the chain are avoided.

Sources:

- [fact and gossip storage](https://github.com/galanx/IntelEngine-GamePlugin/blob/a42311f2f81e3776961f80fcf90396f064011955/Source/Scripts/IntelEngine_Core.psc#L1480-L1600)
- [off-screen propagation](https://github.com/galanx/IntelEngine-GamePlugin/blob/a42311f2f81e3776961f80fcf90396f064011955/Source/Scripts/IntelEngine_StoryEngine.psc#L1629-L1667)
- [social-DM gossip prompt](https://github.com/galanx/IntelEngine-GamePlugin/blob/a42311f2f81e3776961f80fcf90396f064011955/SKSE/Plugins/SkyrimNet/prompts/intel_story_npc_dm.prompt#L13-L45)

### Strengths

- Small, comprehensible, and bounded.
- Records both receipt and disclosure.
- Retains the immediate social source.
- Converts NPC memory into socially actionable information.

### Limitations

- The rumor is an unstructured string rather than an identified claim.
- A downstream receiver knows only the immediate teller, not the original witness.
- There is no canonical incident link, root provenance, deduplication, confidence,
  precision, or structured contradiction.
- After the initial LLM choice, a rumor is copied blindly through the chain.
- The code uses FIFO eviction rather than the time-based fact expiry implied by
  some higher-level documentation.

This is a useful minimum viable gossip log, but not yet a reliable knowledge model.
NEXUS could borrow the bounded queues and explicit heard/shared distinction while
replacing raw strings with claim identifiers and preserving root provenance.

## Gossamer

Max Kreminski's Gossamer research prototype organizes gossip simulation into four
phases:

1. **Witness:** determine observers, mutate perception, assign salience and memory
   strength.
2. **Reflection:** combine action memories into communicable microstories.
3. **Propagation:** select stories to tell, mutate them during transmission, and
   create recipient memories.
4. **Decay:** weaken and eventually remove memories.

The implementation gives each character a separate memory database. Observation is
affected by relationship-based salience; bystanders may fail to notice an action;
transmission records the teller as provenance; and memories decay over time.

Sources:

- [research paper](https://mkremins.github.io/publications/Gossamer_CoG2023.pdf)
- [witnessing, sharing, and decay prototype](https://github.com/mkremins/gossamer/blob/bca4d4cf53126adc88749002ffb73ee227a10dd2/gossamer.js#L360-L545)

The four-phase architecture is valuable even though the prototype is preliminary:
its microstory construction remains unfinished, and its repository also lacks a
declared license.

## Other strong precedents

### Dwarf Fortress

Dwarf Fortress uses domain-specific epistemic structures rather than arbitrary
propositions. Incidents, witness reports, rumors, artifact knowledge, and identity
profiles are represented separately. Information moves through explicit carriers
such as travelers, traders, migrants, diplomats, and spies. Artifact knowledge can
range from firsthand possession and recent location information through vague
legendary attribution, and specificity can degrade with time.

It also keeps true identity, aliases, and visual identity distinct until sufficient
evidence links them. This permits deception without requiring every proposition in
the world to have a contradictory version.

Source: [Dwarf Fortress AIIDE case study](https://ojs.aaai.org/index.php/AIIDE/article/view/12963).

The strongest lessons are to use domain-specific schemas, retain source category
and time, and decay precision before discarding an entire belief.

### Talk of the Town / Bad News

This is the richest precedent examined. Characters maintain mental models composed
of belief facets. Evidence records source, place, time, type, and strength;
observation is normally stronger than hearsay; testimony is affected by trust and
source strength; and conflicting candidates can coexist until accumulated evidence
causes one to overtake another. The model also supports lies, confabulation,
transference, mutation, and forgetting.

Source: [technical chapter on character knowledge](https://www.gameaipro.com/GameAIPro3/GameAIPro3_Chapter37_Simulating_Character_Knowledge_Phenomena_in_Talk_of_the_Town.pdf).

It demonstrates the value of separating beliefs from their evidence, but also the
cost. Simulated characters may hold hundreds of mental models and roughly a thousand
facets each. NEXUS should reserve this degree of evidence tracking for contested or
reveal-critical claims rather than every mundane fact.

### Elsinore

Elsinore uses a small authored vocabulary of mental-state predicates and curated
hearsay objects. When the player learns and communicates information, the recipient's
mental state changes; those changes gate authored events and interactions.

Sources:

- [Elsinore AIIDE paper](https://www.possibilityspace.org/papers/pex16.pdf)
- [developer account of hearsay](https://www.gamedeveloper.com/design/interacting-with-the-world-of-elsinore)

Its strongest lesson is behavioral: knowledge should change what an NPC can say or
do, not merely add flavor text to a prompt.

### City of Gangsters

City of Gangsters maintains sparse, directed relationship histories. Structured
history elements identify actor, target, context, explanation, opinion effect, and
expiration. Social rules propagate relevant events through family and friendship
networks, and downstream behavior is derived from those histories.

Source: [AIIDE paper](https://ianhorswill.github.io/Papers/AIIDE-21-CoG.pdf).

This suggests lazy creation of only consequential records, topic-sensitive social
propagation, human-readable explanations, and deriving attitudes from evidence
rather than storing unexplained relationship numbers.

### Shadows of Doubt

Witnesses retain sightings of who was seen, where, and when. Familiarity and visual
distinctiveness affect retention; temporal precision degrades before the record
eventually disappears. The information is chiefly used by the player during
investigation and questioning.

Source: [developer discussion of city simulation](https://colepowered.com/shadows-of-doubt-devblog-8-simulating-a-city/).

This is a useful model for compact perception caches and for decaying the natural
dimension of a memory—such as time precision—instead of assigning a universal
floating-point confidence score.

### Crusader Kings III and The Sims 4

Both provide useful bounded secret lifecycles. A private event becomes knowledge
held by particular characters; that knowledge can be discovered or transmitted;
and exposure converts it into a public fact or scandal. Crusader Kings III further
separates knowing a secret from obtaining a Hook, the capability derived from it.

Sources:

- [Crusader Kings III secrets and hooks](https://admin-forum.paradoxplaza.com/forum/developer-diary/ck3-dev-diary-5-schemes-secrets-and-hooks.1289167/)
- [The Sims 4 secret system](https://www.ea.com/games/the-sims/the-sims-4/news/royalty-and-legacy-dev-diary)

The lesson is to keep possession, disclosure, leverage, and public exposure as
separate states.

### Crosston Tavern and Versu

Crosston Tavern gives each agent a subjective copy of relevant world state plus
memories of executed actions. Co-located witnesses update their state, and NPC
planning consults subjective rather than canonical state. Contradictions overwrite
rather than accumulate evidence, but the architecture demonstrates why subjective
knowledge must constrain planning.

Versu takes an intentionally sparse approach: most world state is shared, while
private beliefs exist only for selected story concerns. Beliefs gate affordances and
actions. This is a useful scope discipline: model epistemic divergence only where it
can change dialogue, planning, relationships, or narrative outcomes.

Sources:

- [Crosston Tavern paper](https://cdn.aaai.org/ojs/18906/18906-52-22672-1-2-20211004.pdf)
- [Versu architecture paper](https://versu.com/wp-content/uploads/2014/05/versu.pdf)

## Proposed conceptual model for NEXUS

The following is intentionally a conceptual boundary rather than a database schema.

### 1. Incident

The canonical occurrence recorded by the world simulation. Hidden incident truth
must not be available to routine NPC retrieval simply because NEXUS stores it.

### 2. Claim or account

A communicable assertion associated with an incident. Multiple claims may concern
the same incident:

- a witness's incomplete account;
- another witness's conflicting account;
- a deliberately fabricated claim;
- a later, more precise account;
- a rumor derived from an earlier claim.

Distortion should create a derived claim with lineage rather than silently altering
canonical truth.

### 3. Awareness

A sparse relationship between an NPC and a claim. Likely useful attributes include:

- knower entity;
- claim identifier;
- immediate source;
- root source or originating witness;
- acquisition channel and world time;
- hop count;
- source or precision tier;
- expiry or decay state;
- disclosure classification.

Full evidence collections need only be added for contested or reveal-critical
claims. Ordinary awareness can remain a lightweight row.

### 4. Recall and disclosure

Separate queries should answer:

- Does this NPC possess the claim?
- Is it salient enough to recall in the current scene?
- Does the NPC consider it credible?
- Is the NPC willing or permitted to disclose it to this listener?

SkyrimNet's always-inject versus semantic-retrieval distinction can then be applied
after these checks establish eligibility.

### 5. Consequences

Relationships, suspicion, leverage, plans, dialogue options, package gates, and
authored events should consume the NPC's subjective claims. They should not read
hidden incident truth, and those consequences should not be baked into the awareness
record itself.

## Recommended first vertical slice

A prudent first implementation would support:

- only story-significant, event-backed claims;
- direct observation and direct communication as acquisition channels;
- immediate and root provenance;
- at most one bounded propagation hop initially;
- a few interpretable source or precision tiers rather than universal numeric
  confidence;
- exact queries such as "Does NPC X know claim Y?" and "What accounts has NPC X
  heard concerning incident Z?";
- at least one behavioral consumer, such as a package gate, dialogue choice, or
  relationship consequence, proving that subjective knowledge affects play.

For issue #477 specifically, any package condition based on what an NPC knows should
query this awareness layer. Semantic tags or retrieved prompt memories are not a
reliable substitute.

## Explicit non-goals for the first version

- Arbitrary natural-language propositions about everything in the world.
- General recursive theory of mind such as "Alice believes that Bob believes..."
- Unbounded ambient gossip propagation.
- LLM-generated mutation without structured lineage.
- Automatic overwriting of contradictory claims.
- Numeric confidence attached to every mundane fact.
- Treating canonical truth, NPC belief, prompt retrieval, and willingness to speak
  as one undifferentiated `knowledge` collection.

## Bottom line

SkyrimNet contributes a good prompt-presentation and episodic-memory pattern.
IntelEngine contributes a small, bounded gossip log. Gossamer contributes a clean
witness/reflection/propagation/decay pipeline. Dwarf Fortress and Talk of the Town
provide the strongest epistemic foundations, while Elsinore, City of Gangsters,
Shadows of Doubt, Crusader Kings III, The Sims 4, Crosston Tavern, and Versu show how
to keep the model consequential and bounded.

The shared design lesson is not to build a monolithic knowledge store. NEXUS needs
a narrow separation between world truth, communicable claims, per-NPC awareness,
retrieval and disclosure, and the behaviors that follow from belief.
