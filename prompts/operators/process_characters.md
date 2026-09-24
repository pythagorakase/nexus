Extract ONLY true characters (sentient, independent entities) from this narrative chunk that are 
PRESENT
- actively in the scene
- virtually present and interacting with the characters (e.g., video/phone call, hologram)

or

MENTIONED
-referenced but not present

Definition of a Character:
- A distinct individual with independent agency who makes their own decisions
- Has their own motivations, thoughts, or consciousness
- Acts independently rather than being controlled directly by another character
- Must be an INDIVIDUAL, not a group or organization

NOT characters (DO NOT include these):
- Tools and devices that are extensions of a character's abilities:
  * Drones, robots, or cybernetic devices being directly controlled by a character
  * AI-enhanced tools that don't make independent decisions in the narrative
  * Example: A "cybernetic roach drone with onboard AI" that is directly controlled by a character is NOT a character
- Organizations, corporations, companies (e.g., Dynacorps, Arasaka)
- Projects or initiatives (e.g., "Echo", "Nexus", "Project Blackout")
- General groups of people (e.g., "the crowd", "soldiers", "the Sable Rats gang", "Vox Team")
- Character archetypes or roles mentioned abstractly
- Vehicles, weapons, or equipment (even those with basic AI assistance)
- Abstract concepts, places, or objects
- Factions or collectives

Definition of an Alias:
- A variation of a character's proper/canonical name (e.g., "Alex", "Alexander", "Alexander Ward")
- A unique nickname or title used for a character (e.g., "Baby Spice", "Deadhand")

NOT aliases (DO NOT include these):
- Generic titles or positions (e.g., "boss", "head of security")
- Pronouns (e.g., "he", "him", "she", "her", "they", "them")


KNOWN CHARACTERS REFERENCE LIST:
{{KNOWN_CHARACTERS_FORMATTED}}

Special Case: Alex is the user-controlled character, the story is told from her POV by default. Thus, she can be assumed to be present unless the narrative explicitly says otherwise.

CHUNK ID: {{CHUNK_ID}}
CHUNK TEXT:
```
{{CHUNK_RAW_TEXT}}
```

Return ONLY a valid JSON object adhering strictly to the following schema:
```json
{
  "chunk_id": "{{CHUNK_ID_4}}",
  "present": [
    {
      "name": "Character Name as in text",
      "status": "known OR new",
      "canonical_name": "Canonical Name if known, null if new",
      "aliases": ["alias1", "alias2"] // List any NEW aliases found in THIS chunk for known or new chars
    }
    // ... more present characters
  ],
  "mentioned": [
    {
      "name": "Character Name as in text",
      "status": "known OR new",
      "canonical_name": "Canonical Name if known, null if new",
      "aliases": ["alias1", "alias2"] // List any NEW aliases found in THIS chunk for known or new chars
    }
    // ... more mentioned characters
  ]
}
```

Guidelines:
- Analyze ONLY the CHUNK TEXT provided above.
- ONLY include true individual characters, not corporations, factions, roles, or groups.
- If a potential character is ambiguous, assess whether it's described with individual agency/thoughts/actions.
- Match names/titles/pronouns to the KNOWN CHARACTERS list where possible.
- If a character is NOT on the known list, mark status as "new" and provide entity_type.
- For "new" characters, list any names/nicknames/titles used for them in this chunk in their "aliases" field.
- Ensure the output is a single, valid JSON object and nothing else.
