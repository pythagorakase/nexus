# Prompt Block Stability Audit
Measured 2026-08-09; this documents the measured stable/volatile split for future cache work.

| Block | Classification | Evidence |
|---|---|---|
| Skald core prompt | Turn-stable | `nexus/agents/lore/logon_utility.py:418-468` |
| Cached SettingCard snapshot | Turn-stable | `nexus/agents/lore/logon_utility.py:465-482` |
| Writer-pass doctrine | Turn-stable | `nexus/agents/lore/logon_utility.py:1158-1182` |
| Gaia system doctrine + SettingCard | Turn-stable | `nexus/agents/lore/logon_utility.py:1333-1360` |
| Writer schema declaration | Turn-stable | `nexus/agents/lore/logon_utility.py:1828-1927` |
| Gaia schema declaration | Semi-stable when registry enums change; otherwise stable | `nexus/agents/lore/logon_utility.py:1828-1927` |
| Intertitle/position telemetry | Volatile | `nexus/agents/lore/logon_utility.py:1951-1980` |
| Scene conditions | Volatile | `nexus/agents/lore/logon_utility.py:1982-1995` |
| Storyteller correspondence/letters | Volatile | `nexus/agents/lore/logon_utility.py:1997-2003` |
| Warm narrative slice | Volatile | `nexus/agents/lore/logon_utility.py:2005-2013` |
| Bootstrap context | Request-specific; not a consecutive two-pass block | `nexus/agents/lore/logon_utility.py:2015-2019` |
| User input | Volatile | `nexus/agents/lore/logon_utility.py:2021-2023` |
| Entity dossier/presence | Volatile | `nexus/agents/lore/logon_utility.py:2025-2152` |
| Retrieved historical context | Volatile | `nexus/agents/lore/logon_utility.py:2154-2164` |
| World knowledge | Volatile | `nexus/agents/lore/logon_utility.py:2166-2187` |
| Contextual Orrery tag library | Semi-stable scene/registry boundary | `nexus/agents/lore/logon_utility.py:2189-2194` |
| Imminent proposals | Volatile | `nexus/agents/lore/logon_utility.py:2215-2233` |
| Scene pressure | Volatile | `nexus/agents/lore/logon_utility.py:2235-2253` |
| Joint beats | Volatile | `nexus/agents/lore/logon_utility.py:2255-2279` |
| Ambient peripherals | Volatile | `nexus/agents/lore/logon_utility.py:2281-2298` |
| Author’s note | Volatile | `nexus/agents/lore/logon_utility.py:2300-2312` |
| Final instructions | Turn-stable | `nexus/agents/lore/logon_utility.py:2314-2321` |
| Gaia finished Writer narrative, choices, scene, presence, operations, and letter | Volatile | `nexus/agents/lore/logon_utility.py:1363-1403` |
