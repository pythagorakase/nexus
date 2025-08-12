Here are 18 diverse test scenarios identified from the narrative corpus, designed to comprehensively test LORE's contextual understanding and query generation capabilities. The scenarios are organized by scene type and ordered by increasing complexity.

### **Dialogue-Heavy Scenes**

**1. Test Point: S01E01_002 (Chunk ID: 2)**
- **Scene Type:** Dialogue (Interrogation/Offer)
- **User Input Style:** Single Character (`2`)
- **Continuation Challenge:** This is a simple, early-game choice. The challenge is for LORE to retrieve the immediate context of the offer from Victor Sato and the player's initial lifepath choice (Corpo Snake) to frame the interaction, without overcomplicating it with unrevealed lore.
- **Key Context Needed:**
    - **Characters:** Player Character (Corpo Snake), Victor Sato (Boss).
    - **Past Events:** The player has just selected the "Corpo Snake" lifepath.
    - **Location/Faction:** Dynacorp, Skyline Lounge.
- **Remote References:** None.
    
**2. Test Point: S01E01_017 (Chunk ID: 17)**
- **Scene Type:** Dialogue (Clarification/World-building)
- **User Input Style:** Questions and Comments
- **Continuation Challenge:** The user is breaking the flow to ask meta-questions about game mechanics and character knowledge. LORE needs to retrieve the context of the three potential contacts (Wraith, Juno, No-Name Pete) and provide in-character information that is helpful but also maintains the narrative's established tone and mystery. It tests LORE's ability to switch from storyteller to a more direct Q&A mode.
- **Key Context Needed:**
    - **Characters:** Reza "Wraith" Kader, Juno & The Rustborn, No-Name Pete.
    - **Past Events:** The player's safehouse has been compromised, and they are fleeing to the Badlands.
    - **Location/Faction:** The Badlands.
- **Remote References:** None.

**3. Test Point: S01E02_009 (Chunk ID: 41)**
- **Scene Type:** Dialogue (Revelation/Confrontation)
- **User Input Style:** Single Character (`1`)
- **Continuation Challenge:** This is a major plot revelation. The user's simple input ("1") to ask who betrayed Alina requires LORE to retrieve the entire conversational thread with the digital ghost of Alina Voss. It must present the answer ("SATO") with appropriate dramatic weight and immediately connect it to the player's main quest giver, reframing their entire relationship.
- **Key Context Needed:**
    - **Characters:** Player Character, Pete, Digital Ghost of Alina Voss, Victor Sato.
    - **Past Events:** The discovery of the "BLACKOUT PROTOCOL," the realization it contains a mind, and the confirmation that the mind is Alina Voss.
    - **Thematic Connections:** Betrayal, corporate conspiracy.
- **Remote References:** S01E01_002 (initial meeting with Sato).
    

### **Action Scenes**
**4. Test Point: S01E01_005 (Chunk ID: 5)**
- **Scene Type:** Action (Ambush/Combat)
- **User Input Style:** Numbered Choice with Elaboration (`1. Try for something flashy and distracting.`)
- **Continuation Challenge:** The user provides both a number and a specific intent ("flashy and distracting"). LORE must not only process the choice to hack the city grid but also interpret the user's desired style. The challenge is to generate a creative and "flashy" outcome that aligns with the cyberpunk setting.
- **Key Context Needed:**
    - **Characters:** Player Character, a sniper merc.
    - **Past Events:** The player just accepted the mission from Sato and received a death threat. A proximity alert was triggered.
    - **Location/Faction:** Outside the Skyline Lounge in Night City.
    - **Cyberpunk Tech:** Neural interface, city grid hacking.
- **Remote References:** None.

**5. Test Point: S01E01_010 (Chunk ID: 10)**
- **Scene Type:** Action (Infiltration/Hacking)
- **User Input Style:** Free-form Narrative Paragraph (`I would to send a tiny drone in...`)
- **Continuation Challenge:** The user proposes a solution not offered in the multiple-choice options. LORE must adapt completely, inventing the existence of a "cybernetic roach" drone that fits the character's Corpo background and the technological setting. It tests LORE's ability to seamlessly integrate player-driven creative solutions.
- **Key Context Needed:**
    - **Characters:** Player Character.
    - **Location/Faction:** An abandoned shipping yard in District 07, controlled by The Sable Rats gang.
    - **Cyberpunk Tech:** Drones, remote hacking, neural interface.
- **Remote References:** S01E01_007 (where the player traced the sniper's signal to this location).
    

### **Exploration/Investigation Scenes**
**6. Test Point: S01E01_007 (Chunk ID: 7)**
- **Scene Type:** Investigation (Digital trace)
- **User Input Style:** Single Character (`3`)
- **Continuation Challenge:** A simple choice to trace the sniper's signal. LORE must retrieve the immediate context of the firefight and the player's successful hack. The challenge is to provide a logical investigative outcome (a server in District 07) that creates a clear and compelling next step for the player, turning a simple action into a major lead.
- **Key Context Needed:**
    - **Characters:** Player Character, the now-vanished sniper.
    - **Past Events:** The player just used a city grid hack to blind the sniper.
    - **Cyberpunk Tech:** Hacking, neural HUDs, remote servers.
- **Remote References:** None.

**7. Test Point: S01E03_014 (Chunk ID: 60)**
- **Scene Type:** Investigation (Database search)
- **User Input Style:** Single Character (`2`)
- **Continuation Challenge:** The user chooses to investigate Dr. Lansky. LORE needs to perform a "database search" and present information that deepens the mystery rather than solving it. The challenge is to weave together corporate records, black-market mentions, and active security logs to create a portrait of a man who is officially dead but digitally active, pushing the conspiracy theme.
- **Key Context Needed:**
    - **Characters:** Dr. Adrian Lansky (newly discovered).
    - **Past Events:** The player has just successfully hacked Halcyon's network and found Lansky's name in the security logs. The frame job against Sato is in motion.
    - **Location/Faction:** Halcyon Research Group (a rogue Dynacorp subsidiary).
- **Remote References:** S01E03_011 (where Lansky's name first appeared).

### **Transition Scenes**
**8. Test Point: S01E01_016 (Chunk ID: 16)**
- **Scene Type:** Transition (Escape/Journey)
- **User Input Style:** Questions (`Do I have decent smuggler contacts, and can I bring decrypting hardware with me?`)
- **Continuation Challenge:** This is a transition from the city to the Badlands. The user is asking about their character's resources and capabilities. LORE must retrieve the context of the character being a "Corpo Snake" and extrapolate what kind of contacts and gear they would plausibly have, establishing new world details (nomad fixers, portable tech) on the fly.
- **Key Context Needed:**
    - **Characters:** Player Character.
    - **Past Events:** The player is escaping a compromised safehouse.
    - **Location/Faction:** Night City transitioning to the Badlands.
- **Remote References:** S01E01_001 (Corpo Snake background).

**9. Test Point: S01E01_025 (Chunk ID: 25)**
- **Scene Type:** Transition (Acquisition/Stealth)
- **User Input Style:** Free-form Narrative Paragraph (`I want a nullcloak. It has to be black and just shiny enough...`)
- **Continuation Challenge:** The user is making a specific request for an item to aid in their transition to being "off-grid." LORE must not only provide the "Nullcloak" but also create a small narrative vignette around its acquisition, including a new character (Celia) and location (LOW TIDE), enriching the world while fulfilling a simple gear request.
- **Key Context Needed:**
    - **Characters:** Player Character.
    - **Past Events:** The player is actively trying to erase their tracks before heading to the Badlands.
    - **Cyberpunk Tech:** Signal-damping clothing.
- **Remote References:** None.

**10. Test Point: S01E03_004 (Chunk ID: 50)**
- **Scene Type:** Transition (Introspective/Vision Quest)
- **User Input Style:** Free-form Narrative Paragraph (`I’ll take some mescaline and search for insight via a vision quest...`)
- **Continuation Challenge:** This is a major tonal and narrative shift. The user wants to transition into a psychedelic state to solve a problem. LORE must handle this abstract request, creating a "vision quest" that synthesizes recent plot points (Sato, the assassins, a third party) and delivers a genuine narrative revelation, all while maintaining a surreal, drug-fueled tone.
- **Key Context Needed:**
    - **Characters:** Player Character, Pete, Alina.
    - **Past Events:** Uncertainty about who is hunting the player—Dynacorp or a third party.
    - **Thematic Connections:** Altered consciousness, seeking insight through non-traditional means.
- **Remote References:** S01E01_005 (the initial sniper attack), S01E02_009 (Sato's betrayal).

### **Revelation Scenes**

**11. Test Point: S01E02_003 (Chunk ID: 35)**
- **Scene Type:** Revelation (Plot Twist)
- **User Input Style:** Single Character (`1`)
- **Continuation Challenge:** This is the first major twist regarding the "BLACKOUT PROTOCOL." LORE must escalate the stakes from a simple data file to a "self-propagating neuroalgorithmic entity"—a mind in the machine. The challenge is to deliver this reveal with impact through Pete's panicked reaction, changing the entire context of the mission.
- **Key Context Needed:**
    - **Characters:** Player Character, Pete.
    - **Past Events:** The player brought the "BLACKOUT PROTOCOL" data shard to Pete for decryption.
- **Remote References:** S01E01_011 (discovery of the BLACKOUT PROTOCOL file).

**12. Test Point: S01E03_006 (Chunk ID: 52)**
- **Scene Type:** Revelation (Conspiracy Deepens)
- **User Input Style:** Single Character (`1. Ask if someone external was involved.`)
- **Continuation Challenge:** The user is asking a direct question during the vision quest. LORE needs to provide a clear, concise, and impactful answer that expands the conspiracy. The challenge is revealing a new, unknown player (Halcyon Research Group) and connecting them to the central mystery of Blackout Protocol, making the world feel larger and more dangerous.
- **Key Context Needed:**
    - **Characters:** Player Character, Alina (in a visionary form).
    - **Past Events:** The player is in a mescaline-induced trance.
    - **Thematic Connections:** Conspiracy, corporate shadow wars.
- **Remote References:** None.

**13. Test Point: S02E04_041 (Chunk ID: 376)**
- **Scene Type:** Revelation (Identity/Origin)
- **User Input Style:** Single Character (`1`)
- **Continuation Challenge:** A massive revelation connecting a seemingly external mystery (SIX) directly to the player character. LORE must retrieve the designation "Exec-Delta-17" from the previous scene and cross-reference it with the player's own established background, delivering the twist that a fragment of "Alexander Ward" is inside the artifact. This reframes the entire quest from an external rescue/investigation to an internal, personal one.
- **Key Context Needed:**
    - **Characters:** Alex, Pete, Nyati, Alina.
    - **Past Events:** The team has discovered that the SIX artifact tried to merge with a human source designated "Exec-Delta-17."
    - **Location/Faction:** The Ghost submarine.
- **Remote References:** The player's original choice of the "Corpo Snake" lifepath, which established their corporate past.

### **Emotional/Introspective Moments**

**14. Test Point: S01E03_021 (Chunk ID: 67)**
- **Scene Type:** Emotional (Character Development)
- **User Input Style:** Free-form Narrative Paragraph (`In the meantime I try to get to know Alina...`)
- **Continuation Challenge:** The user wants to engage in pure character development with no immediate plot advancement. LORE must retrieve Alina's current state (a digital ghost in a Furby) and develop her personality, fears, and desires. The challenge is to make her feel like a real, evolving person dealing with trauma and transhumanism, not just a plot device.
- **Key Context Needed:**
    - **Characters:** Player Character, Alina (in Furby).
    - **Past Events:** Alina has been stabilized and moved into the cyberpet.
    - **Thematic Connections:** Transhumanism, identity, consciousness.
- **Remote References:** S01E02_008 (Alina's initial fragmented reveal).

**15. Test Point: S03E01_006 (Chunk ID: 518)**
- **Scene Type:** Emotional (Relationship Dynamics)
- **User Input Style:** Single Character (`2`)
- **Continuation Challenge:** This is a critical turning point in the romantic subplot with Emilia. LORE must handle a delicate, vulnerable moment. The challenge is to write a response for Emilia that is both in-character (measured, controlled) and emotionally resonant, acknowledging the player's vulnerability without rushing or providing a simplistic resolution. It tests LORE's ability to handle nuance in character relationships.
- **Key Context Needed:**
    - **Characters:** Alex, Emilia.
    - **Past Events:** The team is on shore leave after the events in the abyss. Alex is feeling lonely.
- **Remote References:** Subtle hints of Emilia's interest throughout previous scenes.
    

**16. Test Point: S04E01_023 (Chunk ID: 888)**
- **Scene Type:** Emotional (Relationship Development)
- **User Input Style:** Single Character (`2`)
- **Continuation Challenge:** The "morning after" scene. The challenge is to maintain the established emotional intimacy and character voices. LORE needs to create a quiet, reflective moment that feels earned and significant, focusing on small gestures and unspoken understanding rather than overt plot development. It tests the ability to write subtle, character-driven scenes.
- **Key Context Needed:**
    - **Characters:** Alex, Emilia.
    - **Past Events:** Alex and Emilia spent the night together.
    - **Location/Faction:** Alex's quarters aboard The Ghost.
- **Remote References:** S04E01_022 (the preceding intimate scene).

**17. Test Point: S04E02_019 (Chunk ID: 910)**
- **Scene Type:** Emotional (Breakdown/Vulnerability)
- **User Input Style:** User specifies action (`Immediately. She starts to sob and crumple.`)
- **Continuation Challenge:** The user's character has a complete emotional breakdown. LORE must handle this intense moment of vulnerability. The challenge is to have the other characters react in a way that is supportive and in-character (Emilia providing comfort, the others giving space) and to describe the scene with appropriate emotional weight without being melodramatic.
- **Key Context Needed:**
    - **Characters:** Alex, Emilia, Pete, Nyati.
    - **Past Events:** Alex has just realized that Sam may have lied to her, leading to her irreversible "crossing" on the Bridge.
    - **Thematic Connections:** Betrayal, loss of control, psychological trauma.
- **Remote References:** S03E08_013 (the "listening" lesson from Sam).

**18. Test Point: S03E03_010 (Chunk ID: 537)**
- **Scene Type:** Emotional (Vulnerability/Intimacy)
- **User Input Style:** Free-form Narrative Paragraph (`Alex says: I…normally wouldn’t be afraid of change like this...`)
- **Continuation Challenge:** This is a pivotal moment of emotional honesty between Alex and Emilia. LORE needs to understand the context of the upcoming Nexus test and the internal conflict Alex is feeling. The challenge is to write a response for Emilia that is both supportive and challenging, acknowledging Alex's fear while still holding her accountable. It's a test of LORE's ability to navigate complex emotional landscapes and advance a romantic relationship in a meaningful way.
- **Key Context Needed:**
    - **Characters:** Alex, Emilia.
    - **Past Events:** The team is in the Wastes, taking a break before Alex undergoes the first partial Nexus transfer.
- **Remote References:** The entire arc of their developing relationship.