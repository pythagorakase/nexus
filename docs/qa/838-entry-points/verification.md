# Strangeness Entry Points Verification

Work order 838-S3; issue #838; branch `claude/838-zero-spend-entry-checks`, cut from `origin/main` at `9fff6a75`. Run on 2026-10-01 from 2026-10-01T05:01:29Z to 2026-10-01T05:02:01Z (UTC). No migration, no product code change, no paid call.

## Lane and Sequencing Checks

The lane is 8012, the nightly-QA lane, because the QA kit was idle by all three checks, run just before the proof:

```text
$ lsof -nP -iTCP:8012 -sTCP:LISTEN
(exit 1)
$ pgrep -fl scripts/qa_shift
(exit 1)
$ newest shift_state.json: /Users/pythagor/nexus/temp/qa_night_2026-10-01_043326Z/shift_state.json
status = finished
```

## Proof Command and Tail

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
env -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 NEXUS_GATEWAY_PORT=8012 NEXUS_PROOF_EXPORT_EVIDENCE=1 $PY -m pytest -q -s -p tests.dbname_audit tests/proofs/proof_weird_entry_points.py
```

```text
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: mock, postgres, qa640_838_browser_*, qa640_838_cli_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
2 passed, 2 warnings in 30.92s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

`mock` in the audit's target list is the TEST provider's canned-response database: the in-process gateway's TEST wizard path reads it with a `SELECT` through `query_wizard_cache` (`nexus/api/wizard_chat.py:734`, `nexus/api/mock_openai.py:77`). It is neither an owner target nor written.

## CLI Walk: `nexus continue --weird high`

Recorded requests (`cli-requests.json`): one save per CLI call (six calls), then one transition carrying the level.

| # | Method | Path | Request | Status | Response |
| --- | --- | --- | --- | --- | --- |
| 1 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 2 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 3 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 4 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 5 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 6 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 7 | POST | `/api/story/new/transition` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"retrograde": {"enabled": false, "skip_reason": "mock_wizard_model"}}` |

Clone reads (`cli-clone-reads.json`); after each call that left the slot in wizard mode, `GET /api/slot/4/state` also reported `weird_level: "high"`:

Clone `qa640_838_cli_5b7c00013925`.

| Read | `weird_level` | `new_story_creator` rows | `genesis_weird` |
| --- | --- | --- | --- |
| after setup | high | 1 | NULL |
| after step 1 | high | 1 | NULL |
| after step 2 | high | 1 | NULL |
| after step 3 | high | 1 | NULL |
| after step 4 | high | 1 | NULL |
| after transition | no row | 0 | NULL |

Retrograde is skipped for the TEST model by design (`nexus/api/new_story_flow.py:568`), so `genesis_weird` stays NULL after the transition, and the transition clears the wizard cache.

### CLI Transcript (`cli-transcript.txt`)

```text
$ nexus continue --slot 4 --model TEST --weird high
I am Skald, your guide through the creation of new worlds and stories. Welcome to NEXUS. What kind of story speaks to you today?


Choices:
  1. Science Fiction — cyberpunk streets, space operas, near futures
  2. Fantasy — high magic, gritty medieval, urban supernatural
  3. Horror — psychological dread, cosmic terror, survival
  4. Historical — any era, with or without a twist

[Wizard Phase: setting]

$ nexus continue --slot 4 --accept-fate --weird high
Generating artifact...

=== World Document ===
  genre: cyberpunk
  secondary_genres: scifi, noir
  world_name: Neon Palimpsest
  time_period: Late 21st century
  tech_level: near_future
  magic_exists: False
  political_structure: City-states ruled by corporate syndicates under a hollowed-out international council
  major_conflict:
    A quiet but escalating war between ubiquitous surveillance states and decentralised ghost networks fighting to erase, rewrite, or liberate identity data
  tone: dark
  themes:
    - memory and identity
    - surveillance vs. secrecy
    - corporate feudalism
    - urban decay and resilience
  cultural_notes:
    Most people maintain multiple overlapping identities: legal, corporate, and illicit. Reputation scores are more valuable than currency, and social interactions are subtly gamified via augmented reality overlays. Street cliques adopt glitch aesthetics and repurposed corporate mascots as tribal markers. Physical cash is taboo but prized in black markets. Public space belongs to advertisers; private space is a luxury of the ultra-rich; everyone else lives in liminal zones—rooftops, maintenance shafts, transit corridors.
  language_notes:
    A fractured global argot mixes compressed English, Mandarin loanwords, Spanish slang, and corporate jargon. Handles matter more than birth names. Brands and megacorps are used as verbs. Police are called "compliance"; prisons are "cold storage"; dying offline is "true blank".
  geographic_scope: continental
  diegetic_artifact:
    // EXCERPT FROM ORIENTATION PACKET 1.1
    // DISTRIBUTED TO PROVISIONAL CITIZENS OF NEON PALIMPSEST
    // PROPERTY OF THE INTERCITY COUNCIL (ICC) AND ITS CORPORATE PARTNERS
    
    WELCOME TO THE CITY THAT REMEMBERS YOU BETTER THAN YOU REMEMBER YOURSELF.
    
    You are reading this because one or more of your identities has been granted provisional footing in Neon Palimpsest, an urban continuum stretching from the flooded lowlands of old Amsterdam through the vertical spires of the Rhine-Ruhr arcology belt. The maps still show national borders. Our streets do not.
    
    I. ON SOVEREIGNTY
    
    Neon Palimpsest is an accord, not a nation. The Intercity Council exists to ratify what the Syndicates have already decided: water allocations, network bandwidth, acceptable protest densities.
    
    You will encounter three primary powers:
    
    • The Syndicates – corporate houses with legacy charters: data-mining dynasties, biofab cartels, logistics guilds that own every road you walk and drone that passes overhead. Their logos hang where flags used to.
    
    • Compliance Directorates – patchwork security forces contracted out by the Syndicates and nominally aligned with the Council. You will know them by their mirrored visors and the way people stop talking when they enter a room.
    
    • Ghost Networks – unlicensed collectives of hackers, archivists, smugglers, and ex-employees who refuse to be updated to the latest terms of service. They are officially myths. You will know them by the gaps in the record where their names should be.
    
    No single entity rules the city. Instead, hundreds of overlapping jurisdictional meshes settle over you like spiderwebs of fine print. You will break a contract today without knowing it. The penalty will arrive before the explanation.
    
    II. ON MEMORY
    
    All citizens of Neon Palimpsest are subject to Continuous Experience Capture (CEC) in public zones. Your movements, purchases, gestures, and biometric flares are translated into behavioral metrics and stored in distributed ledgers owned by various partners.
    
    This is for your safety.
    
    Your Personal Narrative Score (PNS) will determine where you can live, what contracts you are offered, which doors open, how often the transit drones "happen" to arrive on time for you. A clean, consistent story—no unexplained blackouts, no contradictory affiliations—will be rewarded.
    
    Of course, stories can be edited.
    
    The city’s greatest unspoken trade is in memory. Not the blunt theft of accounts and passwords—any child with a cracked patch of firmware can scrape those—but the precise erasure of a night, the insertion of a credential you never earned, the quiet relocation of an incriminating timestamp.
    
    Rumors persist of deep Ghost black-libraries where entire lives can be rewritten: felons reborn as mid-level analysts, test subjects reconstructed as missing heirs. The Syndicates denounce this as impossible. Their denials are very carefully worded.
    
    III. ON SPACE
    
    Neon Palimpsest is built in layers.
    
    At street level: the Glow. Saturated holographic signage fights the rain; AR halos bloom around storefronts, people, stray dogs. You will rarely see the actual material of walls and pavement—only their branded skins.
    
    Above: the Stacks. Informal architectures in welded steel and polymer, home to freelancers, undocumented workers, and mid-tier contractors. Rooftop gardens filter greywater. Micro-ports handle personal drones like gnats clustering at light.
    
    Below: the Roots. Transit arteries, data trunk-lines, storm tunnels converted into unlisted housing and server warrens. Here, the AR fog thins; projectors are sparse. What is remembered belowground is remembered on purpose.
    
    The higher you climb, the more curated reality becomes. At the very top—executive decks, cloud-bridged sky-lobbies—sunlight is rationed via subscription, and even the horizon is a licensed experience.
    
    IV. ON CUSTOM
    
    You will not be asked your real name.
    
    Instead, you will present a handle, a QR sigil, or a reputation hash. People will search you before they greet you. Expect strangers to know your last ten purchases and your last three viral posts. Expect them not to know your eye color, your scent, the sound of your unfiltered voice.
    
    To decline tagging an interaction is a mild insult. To go fully offline in company is an act of aggression. Only the powerful can afford privacy without consequence.
    
    Physical cash exists. You may see it change hands in the Roots, glinting quietly in maintenance alcoves, passed between people whose AR halos flicker with intentional static. If you are offered notes or coins, understand: what you are buying cannot appear on any ledger.
    
    V. ON DANGER
    
    The city does not want you dead. It wants you predictable.
    
    Unhoused bodies are scooped into sleep programs. Dissidents are funneled into "opinion pilot" groups where their outrage can be modeled, monetized, and steered. Violence is licensed like software: gangs pay for the right to conduct visible theatrics on designated blocks, preferably under the watchful gaze of sponsored drones.
    
    The true violence is quiet: a credibility score nudged downward until your rent spikes and your doctor unsubscribes; a single red flag on a transit corridor that reroutes you every time a certain person enters a station; a background process that harvests your dreams for marketable patterns.
    
    Here is the thing you must understand: in Neon Palimpsest, the line between who you are and who your record says you are has snapped. What you remember doing matters less than what the city remembers for you.
    
    VI. ON OPPORTUNITY
    
    For those willing to navigate the gaps, this is a golden age.
    
    Every surplus data-cache, every redundant backup server, every half-scrubbed metadata field is a doorway. Ghost runners and identity tailors make fortunes walking the knife-edge between Syndicate contracts and Ghost favors. Courier-kids race through the Roots with corroding hard-drives taped under their jackets, carrying truths that no one is supposed to remember.
    
    Somewhere in the Roots, they say, there is a terminal with no input and no output, only a heartbeat of fans in the dark. It does not exist on any network topology. Those who find it may ask the city to forget one thing entirely.
    
    No one agrees on what the price is.
    
    VII. CLOSING REMARKS
    
    You are now part of the palimpsest. Your previous lines have been written over, but not erased. Press your fingers to any rain-slicked wall and you may feel the ghost of an older inscription: a protest slogan, a shop’s name in a dead language, a warning.
    
    The city is always rewriting itself. So can you.
    
    Just remember: every revision leaves a trace.
    
    // END ORIENTATION 1.1
    // DO NOT REDISTRIBUTE WITHOUT PROPER CREDENTIALS

---

[TEST MODE] Welcome to character creation. Based on the world of Neon Palimpsest, which archetypal path speaks to you?

Choices:
  1. The Amnesiac Courier - Someone who wakes with no memory but dangerous skills, hunted by forces they don't remember crossing.
  2. The Double Agent - A figure walking the line between corporate authority and underground resistance, trusted by neither.
  3. The Memory Architect - A technician who can edit, erase, or fabricate identities, now running from their own creations.

[Wizard Phase: character]

$ nexus continue --slot 4 --accept-fate --weird high
Generating artifact...

=== Character Concept ===
  character_state:
    concept:
      archetype: Amnesiac data-smuggler caught between Syndicates and Ghosts
      background:
        They woke three months ago on a maintenance platform halfway up a transit spine, soaked in rain and transit grease, with a courier’s neural mesh burned into their cortex and a single hard-coded instruction pulsing behind their eyes: “Do not trust your own record.” Since then they’ve learned to read the city’s AR halos like weather, drifting through the Glow as an unremarkable runner-for-hire while quietly probing the gaps in their own history. The fragments they’ve retrieved—ghost contracts, redacted lab reports, and a dead handle that still draws Syndicate kill-orders—suggest they once walked the executive decks as a proprietary asset in human skin, then vanished into Ghost custody. Now every job risks reactivating some buried protocol, every scan risks reconciling them with a past the city insists never officially existed.
      name: Kade Imani
      appearance:
        Kade moves like someone always braced for a second impact: shoulders slightly hunched, weight on the balls of their feet, eyes tracking reflections as much as faces. Medium height, wiry build, skin a deep umber mapped with faint latticework scars at the temples where the neural mesh was fused and later ripped out. Their hair is close-cropped on one side, the other left longer and twisted into tight coils that fall over a matte-black ocular implant. In the Glow their AR halo reads as low-saturation static and glitch glyphs—deliberately unfriendly to casual scans. Off-the-rack synth-leather jacket, waterproof cargo pants, and scuffed smart-sneakers hide a surprising number of hardpoints for microdrives and analog tools. Up close, their voice is soft, precise, with a trace of an accent from a coastal region that no longer appears on most maps.
      suggested_traits: status, reputation, obligations
      trait_rationales:
        status:
          In Neon Palimpsest, this character’s formal standing inside a Syndicate or Compliance Directorate will constantly clash with what they secretly do in the Roots, making every action a potential act of treason against their own badge.
        reputation:
          Their public persona—carefully cultivated scores, viral clips, and a curated legend—will be both shield and shackle, forcing them to choose between preserving the story the city believes and acting on what they know.
        obligations:
          They are bound by a binding contract or oath—perhaps to a corporate patron, to a Ghost cell, or to family vanished from the record—so every opportunity comes with a price they cannot easily refuse.
    trait_details:

**Select Three Traits**

0.  Confirm Current Selection

 1. [ ] Allies
      • will actively help you when it matters
      • will take risks for you

 2. [ ] Contacts
      • can be tapped for information, favors, or access
      • limited willingness to take risks for you; may be transactional or arms-length
      • examples: bartender, smuggler, journalist, information broker

 3. [ ] Patron
      • powerful figure who mentors, sponsors, protects, or guides you
      • has own position to protect; may have own agenda

 4. [ ] Dependents
      • lower status/power relative to you, but almost always willing to do what you want
      • rely on you for some degree of support, protection, or guidance
      • may be vulnerable, yet devoted
      • may be capable, but with limited ability to act effectively without your guidance
      • examples: child, employee, subordinate

 5. [X] Status
      • standing within a specific institution, faction, community, or social scene
      • can be formal rank or informal local esteem/clout
      • use this when you are known within that group, even if obscure elsewhere
      • examples: military commission, guild journeyman, corporate board seat, respected neighborhood fixer
      → In Neon Palimpsest, this character’s formal standing inside a Syndicate or Compliance Directorate will constantly clash with what they secretly do in the Roots, making every action a potential act of treason against their own badge.

 6. [X] Fame
      • Fame: how broadly you're recognized beyond any one specific group
      • what the wider world recognizes you for, for better or worse
      • use Status instead when recognition is limited to one faction, institution, community, or subculture
      • may or may not confer influence
      → Their public persona—carefully cultivated scores, viral clips, and a curated legend—will be both shield and shackle, forcing them to choose between preserving the story the city believes and acting on what they know.

 7. [ ] Resources
      • material wealth, equipment, supplies
      • can represent ready access rather than literal possession
      • examples: stock portfolio, buried gold, high loan availability, mineral rights, harvest tithes, access to communal resources

 8. [ ] Domain
      • place or area controlled or claimed by character
      • examples: condominium, uncontested turf, wizard's tower

 9. [ ] Enemies
      • actively opposed to you; will expend energy and take risks to thwart you
      • goals may be limited (jealous colleague who wants to humiliate you) or unlimited (mortal vengeance)

10. [X] Obligations
      • can be to individuals, groups, or concepts
      • examples: oath, debt collector, filial piety
      → They are bound by a binding contract or oath—perhaps to a corporate patron, to a Ghost cell, or to family vanished from the record—so every opportunity comes with a price they cannot easily refuse.

[Wizard Phase: character]

$ nexus continue --slot 4 --accept-fate --weird high
Traits confirmed. Moving to wildcard definition.

---

[TEST MODE] Your character's core is taking shape. Now add a wildcard element that sets them apart. Which resonates with your vision?

Choices:
  1. Ghostprint Key - A pre-Council identity root hidden under their skin that can briefly assume anyone's credentials, but draws dangerous attention with each use.
  2. Neural Echo - Fragmented memories of their erased past that surface unpredictably, sometimes revealing crucial information, sometimes triggering buried protocols.
  3. Dead Man's Archive - A cached data-store of secrets they gathered before their memory was wiped, accessible only through specific emotional triggers.

[Wizard Phase: character]

$ nexus continue --slot 4 --accept-fate --weird high
Generating artifact...

=== Wildcard Trait ===
  character_state:
    concept:
      archetype: Amnesiac data-smuggler caught between Syndicates and Ghosts
      background:
        They woke three months ago on a maintenance platform halfway up a transit spine, soaked in rain and transit grease, with a courier’s neural mesh burned into their cortex and a single hard-coded instruction pulsing behind their eyes: “Do not trust your own record.” Since then they’ve learned to read the city’s AR halos like weather, drifting through the Glow as an unremarkable runner-for-hire while quietly probing the gaps in their own history. The fragments they’ve retrieved—ghost contracts, redacted lab reports, and a dead handle that still draws Syndicate kill-orders—suggest they once walked the executive decks as a proprietary asset in human skin, then vanished into Ghost custody. Now every job risks reactivating some buried protocol, every scan risks reconciling them with a past the city insists never officially existed.
      name: Kade Imani
      appearance:
        Kade moves like someone always braced for a second impact: shoulders slightly hunched, weight on the balls of their feet, eyes tracking reflections as much as faces. Medium height, wiry build, skin a deep umber mapped with faint latticework scars at the temples where the neural mesh was fused and later ripped out. Their hair is close-cropped on one side, the other left longer and twisted into tight coils that fall over a matte-black ocular implant. In the Glow their AR halo reads as low-saturation static and glitch glyphs—deliberately unfriendly to casual scans. Off-the-rack synth-leather jacket, waterproof cargo pants, and scuffed smart-sneakers hide a surprising number of hardpoints for microdrives and analog tools. Up close, their voice is soft, precise, with a trace of an accent from a coastal region that no longer appears on most maps.
      suggested_traits: status, fame, obligations
      trait_rationales:
        status:
          In Neon Palimpsest, this character’s formal standing inside a Syndicate or Compliance Directorate will constantly clash with what they secretly do in the Roots, making every action a potential act of treason against their own badge.
        fame:
          Their public persona—carefully cultivated scores, viral clips, and a curated legend—will be both shield and shackle, forcing them to choose between preserving the story the city believes and acting on what they know.
        obligations:
          They are bound by a binding contract or oath—perhaps to a corporate patron, to a Ghost cell, or to family vanished from the record—so every opportunity comes with a price they cannot easily refuse.
    trait_selection:
      selected_traits: status, fame, obligations
      trait_rationales:
        status:
          In Neon Palimpsest, this character’s formal standing inside a Syndicate or Compliance Directorate will constantly clash with what they secretly do in the Roots, making every action a potential act of treason against their own badge.
        fame:
          Their public persona—carefully cultivated scores, viral clips, and a curated legend—will be both shield and shackle, forcing them to choose between preserving the story the city believes and acting on what they know.
        obligations:
          They are bound by a binding contract or oath—perhaps to a corporate patron, to a Ghost cell, or to family vanished from the record—so every opportunity comes with a price they cannot easily refuse.
      trait_constraints:
        [0]:
          trait: status
          cold_start_relationships: allowed
        [1]:
          trait: fame
          cold_start_relationships: allowed
        [2]:
          trait: obligations
          cold_start_relationships: allowed
    wildcard:
      wildcard_name: Ghostprint Key
      wildcard_description:
        A slim, matte-black wafer embedded beneath the skin of the protagonist’s left wrist, the Ghostprint Key is an illegal, pre-Council identity root signed by a vanished Ghost Network. When pressed against any sanctioned credential surface—door seals, terminal pads, biometric readers—it briefly convinces the system that the user is whoever they most recently brushed against in the city’s data fog, inheriting that person’s clearances and risk flags for a few precious minutes. It cannot be traced to any current ledger schema, which makes it priceless and terrifying: glitches follow in its wake, audit trails knot themselves, and every use quietly pings dormant watchers who remember the old Ghost signature and want it back, destroyed, or both.
    trait_details:
  character_sheet:
    name: Kade Imani
    summary: A Amnesiac data-smuggler caught between Syndicates and Ghosts
    appearance:
      Kade moves like someone always braced for a second impact: shoulders slightly hunched, weight on the balls of their feet, eyes tracking reflections as much as faces. Medium height, wiry build, skin a deep umber mapped with faint latticework scars at the temples where the neural mesh was fused and later ripped out. Their hair is close-cropped on one side, the other left longer and twisted into tight coils that fall over a matte-black ocular implant. In the Glow their AR halo reads as low-saturation static and glitch glyphs—deliberately unfriendly to casual scans. Off-the-rack synth-leather jacket, waterproof cargo pants, and scuffed smart-sneakers hide a surprising number of hardpoints for microdrives and analog tools. Up close, their voice is soft, precise, with a trace of an accent from a coastal region that no longer appears on most maps.
    background:
      They woke three months ago on a maintenance platform halfway up a transit spine, soaked in rain and transit grease, with a courier’s neural mesh burned into their cortex and a single hard-coded instruction pulsing behind their eyes: “Do not trust your own record.” Since then they’ve learned to read the city’s AR halos like weather, drifting through the Glow as an unremarkable runner-for-hire while quietly probing the gaps in their own history. The fragments they’ve retrieved—ghost contracts, redacted lab reports, and a dead handle that still draws Syndicate kill-orders—suggest they once walked the executive decks as a proprietary asset in human skin, then vanished into Ghost custody. Now every job risks reactivating some buried protocol, every scan risks reconciling them with a past the city insists never officially existed.
    personality: Personality to be revealed through play.
    trait_1:
      name: status
      description:
        In Neon Palimpsest, this character’s formal standing inside a Syndicate or Compliance Directorate will constantly clash with what they secretly do in the Roots, making every action a potential act of treason against their own badge.
    trait_2:
      name: fame
      description:
        Their public persona—carefully cultivated scores, viral clips, and a curated legend—will be both shield and shackle, forcing them to choose between preserving the story the city believes and acting on what they know.
    trait_3:
      name: obligations
      description:
        They are bound by a binding contract or oath—perhaps to a corporate patron, to a Ghost cell, or to family vanished from the record—so every opportunity comes with a price they cannot easily refuse.
    wildcard_name: Ghostprint Key
    wildcard_description:
      A slim, matte-black wafer embedded beneath the skin of the protagonist’s left wrist, the Ghostprint Key is an illegal, pre-Council identity root signed by a vanished Ghost Network. When pressed against any sanctioned credential surface—door seals, terminal pads, biometric readers—it briefly convinces the system that the user is whoever they most recently brushed against in the city’s data fog, inheriting that person’s clearances and risk flags for a few precious minutes. It cannot be traced to any current ledger schema, which makes it priceless and terrifying: glitches follow in its wake, audit trails knot themselves, and every use quietly pings dormant watchers who remember the old Ghost signature and want it back, destroyed, or both.
    trait_constraints:
      [0]:
        trait: status
        cold_start_relationships: allowed
      [1]:
        trait: fame
        cold_start_relationships: allowed
      [2]:
        trait: obligations
        cold_start_relationships: allowed

---

[TEST MODE] Your character is ready. Now let's craft the opening scene. Which draws you in?

Choices:
  1. The Job You Already Took - Kade wakes on a rattling tram, a courier's satchel handcuffed to their wrist and no memory of accepting the job. The city's ledgers insist the delivery is already in breach.
  2. The Message That Found You - A ghost-frequency ping activates in Kade's burned neural mesh—coordinates and a single word: 'Remember.' Someone from their erased past wants to make contact.
  3. The Face You Used to Wear - Kade spots their own face on a wanted feed, but the name and crimes belong to someone they don't remember being. The bounty is high enough to turn every stranger into a threat.

[Wizard Phase: seed]

$ nexus continue --slot 4 --accept-fate --weird high
Generating artifact...

Retrograde cold-start history:
  skipped (mock_wizard_model)

=== Starting Scenario ===
  seed:
    seed_type: mystery
    title: The Job You Already Took
    situation:
      Three months after waking with no past and a warning not to trust their own record, Kade Imani comes to on a rattling tram in the Roots, rain hammering the metal skin overhead, a courier’s satchel handcuffed to their wrist and a notification blinking in their retinal HUD: “DELIVERY CONFIRMED. PAYMENT PENDING. INCIDENT UNDER REVIEW.” They have no memory of accepting a job, no recollection of how they got the satchel, and yet the city’s ledgers insist they are already in breach of a contract tied to a Syndicate they doesn’t remember working for, and a Ghost cell they don’t remember meeting.
    hook:
      Kade is trapped in a closed loop: the city insists they’ve already done something dangerous and illegal, but their own mind and the physical evidence don’t match—and every system that could prove their innocence also wants to arrest, recruit, or erase them.
    immediate_goal:
      Figure out what is inside the satchel and where, exactly, this “confirmed” delivery was supposed to go before Compliance or the Syndicate’s own fixers catch up.
    stakes:
      If Kade mishandles the satchel or follows the wrong trail, they could reactivate whatever buried protocols still linger in their burned-out neural mesh, condemn themselves as a traitor to a Syndicate whose badge they no longer wear, or become a loose end both corporate and Ghost factions decide to cut.
    tension_source:
      A three-way pressure between Syndicate enforcers auditing the “incident,” Ghost operatives trying to trace their own vanished asset, and Kade’s malfunctioning memory throwing up fragmentary, contradictory flashes tied to the satchel.
    base_timestamp:
      year: 2087
      month: 11
      day: 3
      hour: 22
      minute: 47
      second: 0
    weather:
      Cold, wind-driven rain filtering down from street-level leaks, oppressive humidity, and intermittent brownouts in the tram’s emergency lighting.
    key_npcs:
      - A jittery, low-level Syndicate auditor riding two cars behind, watching Kade’s ledger in real time from a cheap overlay rig.
      - An unregistered medic with Ghost sympathies, slumped across from Kade and pretending to sleep, their AR halo fuzzed out by intentional static.
      - The tram’s AI conductor, its personality core degraded and quietly forking unsanctioned parallel processes in the Roots’ mesh.
    secrets:
      The satchel does not contain a simple data drive but a physical, pre-Council identity ledger page—an artifact that can overwrite modern ledgers with an older, deeper “truth.” Kade’s original self was once a Syndicate-owned identity engineer who helped design the very systems now hunting them, then defected to a Ghost Network that used them to create the Ghostprint Key and this off-ledger identity root. The “job” they supposedly just completed was in fact a forced re-enactment of a mission from their erased past, triggered by a buried protocol in their scarred neural mesh as part of a Syndicate experiment to test whether Ghost-conditioned assets can be remotely reactivated. The Syndicate auditor on the tram is secretly under orders not to arrest Kade but to track where they go if they slip the net, hoping to locate a dormant Ghost black-library node. The medic across from Kade once extracted part of Kade’s memory and hid it inside the tram’s decaying AI conductor; the AI carries within its glitching subroutines a compressed recording of Kade’s betrayal of both Syndicate and Ghost, which, if recovered, would ruin any chance at a clean new identity. Meanwhile, a quiet backdoor in the Ghostprint Key is awakening with each nearby system query, preparing to broadcast Kade’s precise location to a long-silent Ghost frequency that may now be controlled by someone—or something—else.
  location_sketch:
    A place called Spine-9 Rootline Tram 3B in the Rhine-Ruhr Arcology Belt region of Neon Palimpsest Earth. Spine-9 Rootline Tram 3B is a battered, semi-autonomous tram car that crawls through the deepest maintenance tunnels of the Rhine-Ruhr Roots, its scarred composite hull sweating condensation as it ferries a mix of off-ledger passengers, gray-market cargo, and the city’s forgotten processes from one shadowed node to another.

---

The tram shudders as it descends into the Roots, emergency lights flickering amber through condensation-streaked windows. You're aware of the satchel before you're aware of anything else—its weight against your wrist, the cold bite of the handcuff's metal edge where it meets skin. The notification in your retinal HUD pulses insistently: DELIVERY CONFIRMED. PAYMENT PENDING. INCIDENT UNDER REVIEW.

Three months. Three months since you woke in a capsule hotel with no memory of how you got there, a warning scrawled on the mirror in your own handwriting: TRUST NOTHING THEY SHOW YOU. Since then you've been Kade Imani, freelance courier, carefully anonymous, deliberately forgettable. You've built a life from careful routines and strategic silences.

And now this. A job you don't remember taking. A satchel you don't remember receiving. And somewhere in the Syndicate's vast ledger systems, your name flagged for review.

The tram car is sparsely populated at this hour—maintenance workers heading home, a few Roots dwellers with the hollow look of those who've lived too long below the Glow. Two cars back, you caught a glimpse of a figure in a gray coat, AR rig glinting cheap and obvious. Syndicate auditor, almost certainly. They're not even trying to be subtle.

Closer, slumped in the seat across the aisle, someone in a medic's scrubs is pretending to sleep. Their AR halo fuzzes with intentional static—a Ghost tell, or a very good imitation of one. Their breathing is too controlled for genuine sleep.

The tram's ancient AI conductor announces the next stop in a voice that skips and glitches, fragments of old advertisements bleeding through: "Next—pleasure—Spine Junction Nine—optimal pricing—please mind the gap."

Rain hammers against the hull above. Somewhere in the distance, the city's heartbeat of data transactions and identity verifications pulses on, indifferent to your small crisis. But you feel the weight of the satchel, and you know: whatever's inside, it's already changed everything.

Choices:
  1. Examine the satchel more closely, testing the seals for signs of tampering
  2. Study the auditor two cars back—their posture, their equipment, their probable threat level
  3. Make contact with the sleeping medic, a calculated risk to gauge their intentions
```

## Browser Walk: Glyphs, Held Confirm, Transition

The browser story was driven to the Introduction with `nexus continue --slot 4 --model TEST` and four `--accept-fate` calls (`browser-transcript.txt`); its stored level was then NULL. Chromium (1440 x 1000, service workers blocked, `localStorage.activeSlot = 4`) opened `/continue` on the built client.

Recorded requests (`browser-requests.json`): the saves `low`, `medium`, `high`, `low`, then one transition carrying `low`.

| # | Method | Path | Request | Status | Response |
| --- | --- | --- | --- | --- | --- |
| 1 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "low"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "low"}` |
| 2 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "medium"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "medium"}` |
| 3 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "high"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "high"}` |
| 4 | PUT | `/api/story/new/weird` | `{"slot": 4, "weird_level": "low"}` | 200 | `{"status": "recorded", "slot": 4, "weird_level": "low"}` |
| 5 | POST | `/api/story/new/transition` | `{"slot": 4, "weird_level": "low"}` | 200 | `{"retrograde": {"enabled": false, "skip_reason": "mock_wizard_model"}}` |

Clone reads (`browser-clone-reads.json`); each glyph read was matched by `GET /api/slot/4/state`:

Clone `qa640_838_browser_af5a4a78787e`.

| Read | `weird_level` | `new_story_creator` rows | `genesis_weird` |
| --- | --- | --- | --- |
| at the introduction | NULL | 1 | NULL |
| after clicking low | low | 1 | NULL |
| after clicking medium | medium | 1 | NULL |
| after clicking high | high | 1 | NULL |
| while the low save is held | high | 1 | NULL |
| after the held save lands | low | 1 | NULL |
| after transition | no row | 0 | NULL |

While the fourth save (`low`) was held in the browser by `page.route`, Confirm and all three glyphs were disabled, `Strangeness: high` kept `aria-pressed="true"`, and the clone still held `high`. Released with `route.continue_()`, the unchanged request reached the gateway; `low` became pressed and Confirm enabled.

### Screenshots

| File | State |
| --- | --- |
| `glyphs-unset.png` | Introduction, no level stored, all three glyphs unpressed |
| `glyph-low.png` | `low` saved and pressed |
| `glyph-medium.png` | `medium` saved and pressed |
| `glyph-high.png` | `high` saved and pressed |
| `reload-high.png` | after a full page load, `high` alone pressed |
| `confirm-held.png` | the `low` save held: Confirm and glyphs disabled, `high` still pressed |
| `confirm-released.png` | the save landed: `low` pressed, Confirm enabled |

### Console Errors (`console-errors.json`)

- `Failed to load resource: the server responded with a status of 404 (Not Found)` at `http://127.0.0.1:8012/api/dev/backstage/health`
- `Failed to load resource: the server responded with a status of 404 (Not Found)` at `http://127.0.0.1:8012/api/dev/backstage/health`

Both are the client's developer-mode gate probe (`ui/client/src/contexts/DeveloperModeContext.tsx:25`, one per page load). The gateway registers Backstage only when `[orrery.dashboard] enabled` is true (`nexus/api/narrative.py:217`), which is committed false, so the probe answers 404 by design. Neither is on the strangeness path.

## Teardown

The proof's own gateway closed with `nexus down` under its private runtime config (`nothing running`, printed in the proof log). Then:

```text
$ NEXUS_GATEWAY_PORT=8012 NEXUS_API_URL=http://127.0.0.1:8012 $PY -m nexus.cli down
nothing running
(exit 0)
$ lsof -nP -iTCP:8012 -sTCP:LISTEN
(exit 1)
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_838%'"
(exit 0)
```

The owner slots, read only, before and after the run (`save_04` then `save_05`; creator-row digest, then `global_variables` digest):

```text
before:
d41d8cd98f00b204e9800998ecf8427e
a99669a36dbc5dfc0d0caef98eed1732
4b557de44110a547256a0ea12e663553
f661debf7c72bbe18df8ed928151f34b
after:
d41d8cd98f00b204e9800998ecf8427e
a99669a36dbc5dfc0d0caef98eed1732
4b557de44110a547256a0ea12e663553
f661debf7c72bbe18df8ed928151f34b
```

Identical.

## Provider Usage

Paid token usage: 0. Every model call went to the TEST provider's private mock server. Every usage event recorded during the run names model `TEST` (`provider-usage.json`); the mock reports nonzero token counts, so the recorded counts below are the mock's, not spend.

| Test | Events | Models | Seats | Recorded input tokens | Recorded output tokens |
| --- | --- | --- | --- | --- | --- |
| cli | 9 | TEST | skald_single_pass, wizard | 24257 | 6400 |
| browser | 9 | TEST | skald_single_pass, wizard | 24261 | 6400 |
