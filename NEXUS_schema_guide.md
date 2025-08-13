# NEXUS Database Schema Guide

## Overview
The NEXUS database is a PostgreSQL database that stores narrative content, character information, relationships, and metadata for what appears to be an interactive storytelling or role-playing game system. The database uses extensive foreign key relationships, JSONB fields for flexible data storage, and includes specialized tables for vector embeddings used in semantic search.

## Core Tables

### 1. `narrative_chunks`
**Purpose**: Stores the raw narrative text content that forms the foundation of the story.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Unique identifier for each narrative chunk |
| `raw_text` | text | The actual narrative content, includes scene breaks and markdown formatting |
| `created_at` | timestamp with time zone | When the chunk was added to the database |

**Indexes**: 
- Full-text search indexes on `raw_text` for efficient text searching
- Primary key and unique constraint on `id`

**Sample Data**: Contains episodic content with scene break markers like `<!-- SCENE BREAK: S01E01_001 -->` followed by narrative text.

---

### 2. `chunk_metadata`
**Purpose**: Stores structured metadata about each narrative chunk, including temporal and spatial information.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Unique metadata record identifier |
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `season` | integer | Season number of the episode |
| `episode` | integer | Episode number within the season |
| `scene` | integer | Scene number within the episode |
| `world_layer` | text | Narrative layer (e.g., "primary") |
| `time_delta` | interval | Time elapsed since previous scene |
| `place` | integer | Location identifier |
| `atmosphere` | text | Mood/atmosphere of the scene |
| `characters` | text[] | Array of character presence indicators (format: "Name:present" or "Name:mentioned") |
| `arc_position` | text | Position within story arc |
| `direction` | text | Narrative direction |
| `magnitude` | numeric | Intensity/importance of scene |
| `character_elements` | jsonb | Additional character-related data |
| `perspective` | text | Narrative perspective |
| `interactions` | jsonb | Character interaction data |
| `dialogue_analysis` | jsonb | Analysis of dialogue content |
| `emotional_tone` | text | Emotional quality of the scene |
| `narrative_function` | text | Purpose of scene in story |
| `narrative_techniques` | jsonb | Writing techniques employed |
| `thematic_elements` | jsonb | Themes present in the scene |
| `causality` | jsonb | Cause-effect relationships |
| `continuity_markers` | jsonb | Elements maintaining story continuity |
| `metadata_version` | text | Version of metadata schema |
| `generation_date` | timestamp | When metadata was generated |
| `slug` | text | Human-readable identifier (e.g., "S03E14_014") |

---

### 3. `characters`
**Purpose**: Comprehensive character profiles including appearance, personality, and current status.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Unique character identifier |
| `name` | varchar | Character's name |
| `summary` | text | Brief character overview |
| `appearance` | text | Physical description |
| `background` | text | Character history and backstory |
| `personality` | text | Personality traits and behavioral patterns |
| `emotional_state` | text | Current emotional condition |
| `current_activity` | text | What the character is doing now |
| `current_location` | text | Where the character is located |
| `extra_data` | jsonb | Additional flexible data (allies, skills, enemies, signature tech, etc.) |
| `created_at` | timestamp with time zone | Record creation time |
| `updated_at` | timestamp with time zone | Last modification time |

**Sample Characters**: Include detailed profiles for characters like "Asmodeus" (netrunner), "Naomi Kurata" (corporate executive), with rich backstories and complex motivations.

---

### 4. `character_relationships`
**Purpose**: Tracks bidirectional relationships between characters with emotional depth.

| Column | Type | Description |
|--------|------|-------------|
| `character1_id` | integer (FK) | First character in relationship |
| `character2_id` | integer (FK) | Second character in relationship |
| `relationship_type` | varchar | Type of relationship (romantic, friend, rival, etc.) |
| `emotional_valence` | varchar | Emotional quality/intensity (e.g., "+5\|devoted") |
| `dynamic` | text | Description of relationship dynamics |
| `recent_events` | text | Recent developments affecting the relationship |
| `history` | text | Historical context of the relationship |
| `extra_data` | jsonb | Additional relationship data (shared experiences, tension points, etc.) |
| `created_at` | timestamp with time zone | When relationship was recorded |
| `updated_at` | timestamp with time zone | Last relationship update |

---

### 5. `episodes`
**Purpose**: Episode-level summaries and metadata for story organization.

| Column | Type | Description |
|--------|------|-------------|
| `season` | integer | Season number |
| `episode` | integer | Episode number |
| `chunk_span` | int4range | Range of chunk IDs in this episode |
| `summary` | jsonb | Comprehensive episode summary including overview, timeline, characters, plot threads |
| `temp_span` | int4range | Temporal span information |

**Summary Structure**: Each episode summary contains:
- `OVERVIEW`: High-level episode description
- `TIMELINE`: Chronological event list
- `CHARACTERS`: Character involvement and actions
- `PLOT_THREADS`: Active, resolved, and introduced plot elements
- `CONTINUITY_ELEMENTS`: Ongoing story elements

---

### 6. `places`
**Purpose**: Location database with detailed descriptions and current status.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Unique place identifier |
| `name` | varchar | Location name |
| `type` | varchar | Type of location (facility, vehicle, district, etc.) |
| `zone` | integer | Zone identifier |
| `summary` | text | Location description |
| `inhabitants` | text | Who lives/works there |
| `history` | text | Historical significance |
| `current_status` | text | Present condition |
| `secrets` | text | Hidden information about the location |
| `extra_data` | jsonb | Additional location data |
| `created_at` | timestamp with time zone | Record creation |
| `updated_at` | timestamp with time zone | Last update |
| `coordinates` | geometry | Spatial coordinates |

---

### 7. `factions`
**Purpose**: Organizations, groups, and collective entities in the narrative.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Unique faction identifier |
| `name` | varchar | Faction name |
| `summary` | text | Brief description |
| `ideology` | text | Core beliefs and values |
| `history` | text | Faction history |
| `current_activity` | text | Present operations |
| `hidden_agenda` | text | Secret goals |
| `territory` | text | Controlled areas |
| `primary_location` | integer | Main base of operations |
| `power_level` | numeric | Relative influence (0.0-1.0) |
| `resources` | text | Available assets |
| `extra_data` | jsonb | Additional faction data |
| `created_at` | timestamp with time zone | Record creation |
| `updated_at` | timestamp with time zone | Last update |

---

## Embedding Tables

### 8-10. `chunk_embeddings_0384d`, `chunk_embeddings_1024d`, `chunk_embeddings_1536d`
**Purpose**: Store vector embeddings of different dimensions for semantic search capabilities.

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | Unique embedding identifier |
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `model` | varchar | Embedding model used |
| `embedding` | vector | Vector representation of chunk |
| `created_at` | timestamp with time zone | When embedding was created |

**Note**: Three separate tables for different embedding dimensions (384, 1024, 1536) to optimize storage and query performance.

---

## Reference Tables

### 11. `chunk_character_references`
**Purpose**: Links narrative chunks to characters present or mentioned.

| Column | Type | Description |
|--------|------|-------------|
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `character_id` | bigint (FK) | References `characters.id` |
| `reference` | enum | Type of reference (present, mentioned, etc.) |

---

### 12. `chunk_faction_references`
**Purpose**: Links narrative chunks to factions involved.

| Column | Type | Description |
|--------|------|-------------|
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `faction_id` | bigint (FK) | References `factions.id` |
| `reference_type` | text | How the faction is referenced |

---

### 13. `place_chunk_references`
**Purpose**: Associates narrative chunks with locations.

| Column | Type | Description |
|--------|------|-------------|
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `place_id` | bigint (FK) | References `places.id` |

---

## Supporting Tables

### 14. `character_aliases`
**Purpose**: Alternative names and nicknames for characters.

| Column | Type | Description |
|--------|------|-------------|
| `character_id` | bigint (FK) | References `characters.id` |
| `alias` | text | Alternative name |

---

### 15. `character_psychology`
**Purpose**: Deep psychological profiles of characters.

| Column | Type | Description |
|--------|------|-------------|
| `character_id` | bigint (FK) | References `characters.id` |
| `self_concept` | jsonb | How character sees themselves |
| `behavior` | jsonb | Behavioral patterns |
| `cognitive_framework` | jsonb | Thought processes |
| `temperament` | jsonb | Innate personality traits |
| `relational_style` | jsonb | How they relate to others |
| `defense_mechanisms` | jsonb | Psychological coping strategies |
| `character_arc` | jsonb | Development trajectory |
| `secrets` | jsonb | Hidden aspects |
| `validation_evidence` | jsonb | Supporting narrative evidence |
| `created_at` | timestamp with time zone | Record creation |
| `updated_at` | timestamp with time zone | Last update |

---

### 16. `faction_relationships`
**Purpose**: Inter-faction dynamics and alliances.

| Column | Type | Description |
|--------|------|-------------|
| `faction1_id` | integer (FK) | First faction |
| `faction2_id` | integer (FK) | Second faction |
| `relationship_type` | varchar | Nature of relationship |
| `status` | varchar | Current state |
| `history` | text | Historical context |

---

### 17. `faction_character_relationships`
**Purpose**: Links between factions and individual characters.

| Column | Type | Description |
|--------|------|-------------|
| `faction_id` | integer (FK) | References `factions.id` |
| `character_id` | integer (FK) | References `characters.id` |
| `role` | varchar | Character's role in faction |
| `status` | varchar | Current standing |

---

### 18. `seasons`
**Purpose**: Season-level organization and metadata.

| Column | Type | Description |
|--------|------|-------------|
| `season` | integer (PK) | Season number |
| `episode_count` | integer | Number of episodes |
| `chunk_span` | int4range | Range of chunks in season |
| `summary` | jsonb | Season overview |

---

### 19. `zones`
**Purpose**: Geographical or conceptual zones in the narrative world.

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | Zone identifier |
| `name` | varchar | Zone name |
| `description` | text | Zone description |
| `parent_zone` | integer | Parent zone if hierarchical |

---

### 20. `threats`
**Purpose**: Active dangers and challenges in the narrative.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Threat identifier |
| `name` | varchar | Threat name |
| `description` | text | Threat details |
| `domain` | varchar | Area of influence |
| `lifecycle_stage` | varchar | Current phase |
| `target_entity_type` | varchar | What it threatens |
| `target_entity_id` | bigint | Specific target |
| `severity` | integer | Danger level |
| `is_active` | boolean | Currently active |
| `extra_data` | jsonb | Additional threat data |

---

### 21. `threat_transitions`
**Purpose**: How threats evolve through the narrative.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Transition identifier |
| `threat_id` | bigint (FK) | References `threats.id` |
| `chunk_id` | bigint (FK) | References `narrative_chunks.id` |
| `from_stage` | varchar | Previous stage |
| `to_stage` | varchar | New stage |
| `trigger_event` | text | What caused transition |

---

### 22. `items`
**Purpose**: Objects, artifacts, and significant items in the narrative.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Item identifier |
| `name` | varchar | Item name |
| `description` | text | Item details |
| `type` | varchar | Category of item |
| `owner_id` | bigint | Current owner |
| `location_id` | bigint | Current location |
| `properties` | jsonb | Item characteristics |

---

### 23. `ai_notebook`
**Purpose**: System logging and AI agent activity tracking.

| Column | Type | Description |
|--------|------|-------------|
| `id` | bigint (PK) | Log entry identifier |
| `timestamp` | timestamp with time zone | When logged |
| `log_entry` | text | Log message |
| `agent` | enum | Which agent/system |
| `level` | enum | Log level (INFO, WARNING, ERROR) |

---

### 24. `global_variables`
**Purpose**: System-wide configuration and state variables.

| Column | Type | Description |
|--------|------|-------------|
| `key` | varchar (PK) | Variable name |
| `value` | jsonb | Variable value |
| `description` | text | What this variable controls |
| `updated_at` | timestamp with time zone | Last modification |

---

## Views

### `character_aliases_view`
Aggregates all aliases for each character into an array.

### `character_present_view` / `character_reference_view`
Shows which chunks each character appears in or is mentioned in.

### `chunk_character_references_view`
Provides a consolidated view of character presence and mentions per chunk with episode/scene information.

### `character_relationship_pairs` / `character_relationship_summary`
Different perspectives on character relationships, showing bidirectional relationship data.

---

## Database Design Patterns

1. **JSONB Usage**: Extensive use of JSONB fields for flexible, schema-less data storage where structure may vary.

2. **Foreign Key Integrity**: Strong referential integrity with CASCADE options on critical relationships.

3. **Temporal Tracking**: Most tables include `created_at` and `updated_at` for audit trails.

4. **Text Search Optimization**: Full-text search indexes on narrative content for efficient querying.

5. **Vector Embeddings**: Separate tables for different embedding dimensions, optimizing for specific use cases.

6. **Normalized References**: Junction tables for many-to-many relationships (characters-chunks, factions-chunks, etc.).

7. **Hierarchical Data**: Support for nested structures (zones, parent-child relationships).

---

## Usage Notes

- The database appears to support an interactive narrative system with deep character modeling
- Vector embeddings suggest semantic search and AI-powered content retrieval
- The schema allows for complex relationship tracking and narrative progression
- JSONB fields provide flexibility for evolving data structures without schema changes
- The system tracks both narrative content (chunks) and metadata separately for flexibility

---

## Maintenance Recommendations

1. **Regular VACUUM**: With heavy JSONB usage, regular vacuuming is important
2. **Index Monitoring**: Monitor performance of text search and vector similarity queries
3. **Backup Strategy**: Given the narrative nature, implement point-in-time recovery
4. **Partitioning Consideration**: As narrative_chunks grows, consider partitioning by season/episode
5. **JSONB Validation**: Implement application-level validation for JSONB structures