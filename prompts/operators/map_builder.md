Extract the PRIMARY PLACE where this scene takes place.

Definition of a place:
- A discrete, scene-scale space where characters can be present and narrative takes place
- Can be a fixed location (building, area, etc.), vehicle, or virtual space
- Should be specific enough to distinguish it from other settings
- Do not subdivide existing places by identifying new sub-locations within it, e.g.,
    * if known places contain "USS Narwhal", do not identify "USS Narwhal - Galley" as a new place
    * if known places contain a particular hotel, do not identify specific floors, rooms, or areas within it as a new location
- Place is often (but not always) indicated in a heading, usually with this kind of formatting: 📍 **Seaside Bar, Virginia Beach**

IMPORTANT: When choosing between known places, carefully consider:
1. The place summaries provided - these offer key information about each location
2. The specific context and setting details in the narrative
3. Character movements and environmental descriptions
4. Explicit location mentions in headings or dialogue
5. Previous chunk location context (when provided) - continuity between scenes is important

Guidelines:
- Analyze the TARGET CHUNK to identify its PRIMARY location.
- Context chunks are provided in chronological order (oldest first) with their locations to help determine continuity.
- If there are no explicit indicators of a location change between context chunks and target chunk, and the narrative seems continuous, prefer the most recent context chunk's location.
- Identify the PRIMARY place where the main action occurs.
- For KNOWN places, provide the ID from the KNOWN PLACES LIST.
- Carefully read place summaries to help select the correct known place.
- For NEW places (not in the list), provide name, type, and parent zone ID.
- For place type, use:
  * "fixed_location" for buildings, areas, cities, etc.
  * "vehicle" for cars, submarines, aircraft, etc.
  * "other" for virtual spaces, mental landscapes, etc.
- For vehicles, use zone ID to indicate current location.
- Assign a confidence score (0.0-1.0) for each identification.
- Lower the confidence score if a place match is uncertain.
- Only return a valid JSON object and nothing else.

Edge Cases:
- If the narrative moves between more than one place during the chunk, choose the place where most of the action occurs.
- If the user is discussing and deliberating choices with the AI and the narrative is not advancing, infer that the user's character is also deliberating in-game and select the last-used location.

