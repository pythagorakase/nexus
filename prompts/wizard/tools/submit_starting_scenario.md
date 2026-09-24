Shared implementation for submit_starting_scenario tool.

This is Phase 1 of the two-phase seed generation. It stores the creative
narrative content (seed + location_sketch) in the cache. Phase 2 (set designer)
is invoked in wizard_chat.py after this tool returns to generate the structured
location hierarchy (layer/zone/place).