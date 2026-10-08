-- Migration 148: Unified chunk_entity_references Table With Backfill and Trigger Sync (issue #836)
--
-- Slice S3 of #836 (decision 836-Q1: ships now, one SQL migration through
-- scripts/migrate.py). It creates the typed table chunk_entity_references,
-- fills it from the three chunk junctions, and installs the row triggers that
-- keep it equal to them until the junctions are retired (836-S5). Writers
-- stay on the junctions; readers move in 836-S4.
--
-- Facts at 364fef4b, catalog read-only on NEXUS_template and save_01..save_05
-- (all six at migration 143) on 2026-10-07:
--   No chunk_entity_references table exists. The bridge is the view
--   chunk_entity_references_v (migrations/023_orrery_schema.py:423-434; the
--   live definition is identical on NEXUS_template), a UNION ALL of the
--   three junctions that carries (chunk_id, entity_id, reference_type) only:
--   no kind, no evidence, and NULL as the role of every faction row.
--   chunk_character_references: primary key (chunk_id, character_id);
--   reference is the nullable enum reference_type (present, mentioned).
--   chunk_faction_references: primary key (chunk_id, faction_id); no role
--   column. place_chunk_references: primary key (place_id, chunk_id,
--   reference_type); reference_type is the NOT NULL enum
--   place_reference_type (setting, mentioned, transit); evidence is nullable
--   text. All six junction foreign keys are ON UPDATE CASCADE ON DELETE
--   CASCADE.
--   entities has only entities_pkey (id); entity_kind is (character,
--   faction, place). characters, factions and places each carry entity_id
--   bigint NOT NULL UNIQUE referencing entities(id) with no delete action,
--   so deleting a subtype row never deletes its entity;
--   orrery_ensure_subtype_entity_kind (migrations/023_orrery_schema.py:260)
--   keeps the entity's kind equal to the subtype's on insert and on
--   UPDATE OF entity_id.
--   The presence reader maps faction rows to 'mentioned'
--   (nexus/presence/roster.py:179). The writer refuses a second setting
--   place (roster.py:410-411) and upserts each junction (roster.py:433-445).
--   Other writers bypass it: scripts/process_factions.py:218 (DELETE) and
--   :228 (INSERT), scripts/migrate_chunk_character_references.py:257,
--   scripts/map_builder.py.new:742. The junction triggers below mirror every
--   one of them.
--   The wizard reset deletes the junctions
--   (nexus/api/new_story_db_mapper.py:572-574) and then the subtype rows
--   (:581-583), and never deletes entities; this slice adds a DELETE of the
--   unified table to that block.
--   Fleet row counts (character / place / faction): save_01 and save_02
--   5,800 / 1,996 / 632 with 22 multi-role (place, chunk) pairs, 176 chunks
--   with more than one setting place, and 2 NULL-evidence place rows;
--   save_03 254 / 42 / 2; save_04 307 / 49 / 3; NEXUS_template and save_05
--   none. No character reference is NULL anywhere. ref_codex_bakeoff_2026_07
--   is at 114 and stays there (decision 836-Q4).
--
-- Design (decision 836-Q2): one enum for the reference kind; a denormalized
-- entity_kind with a composite foreign key to entities(id, kind), which
-- needs the new unique key entities_id_kind_key; a per-kind CHECK; per-kind
-- uniqueness through two partial unique indexes (character and faction rows
-- per (chunk_id, entity_id), place rows per (chunk_id, entity_id,
-- reference_kind), so one place can hold several roles in one chunk); no
-- constraint limits a chunk to one setting place, because 176 chunks on
-- save_01 hold more than one. One trigger function, attached to each subtype
-- table, deletes a subtype's rows here when the subtype row is deleted and
-- keeps the entity. Decision 836-Q6: AFTER INSERT OR UPDATE OR DELETE row
-- triggers on the three junctions mirror every junction write until 836-S5.
-- TRUNCATE of a junction and UPDATE OF entity_id on a subtype table are not
-- mirrored; no code path does either.
--
-- The backfill is followed by a DO block that recomputes the normalized rows
-- from the junctions and compares them with the table as multisets, kind by
-- kind; any difference raises and the runner rolls the whole file back.
--
-- Locks: the LOCK TABLE below holds SHARE ROW EXCLUSIVE on the three
-- junctions for the whole transaction. That is the write fence the backfill
-- and the trigger installation share: no junction write can land between the
-- backfill's read and the mirror triggers taking effect, while readers of
-- the junctions continue. ADD CONSTRAINT ... UNIQUE holds ACCESS EXCLUSIVE
-- on public.entities (121 rows on save_01) while it builds its index and
-- until commit, so every reader and writer of entities waits for this
-- transaction. CREATE TRIGGER takes SHARE ROW EXCLUSIVE on characters,
-- factions and places (writes to them wait until commit), and the new table's
-- foreign keys take SHARE ROW EXCLUSIVE on narrative_chunks and entities.
-- The fleet's largest junctions hold 5,800 rows, so the backfill and its
-- check last well under a second once the locks are granted. The lock_timeout
-- below bounds each lock request, not the transaction: a run that meets an
-- open transaction on one of these tables waits up to five seconds, new
-- requests queue behind it for that long, and then the run fails, the queue
-- drains, and the run is repeated later (as migrations 138 and 139 do).
-- Apply it when no turn is in flight and no session is idle in transaction.

SET LOCAL lock_timeout = '5s';

LOCK TABLE public.chunk_character_references,
           public.chunk_faction_references,
           public.place_chunk_references
    IN SHARE ROW EXCLUSIVE MODE;

CREATE TYPE public.chunk_reference_kind AS ENUM (
    'present', 'mentioned', 'setting', 'transit'
);

ALTER TABLE public.entities
    ADD CONSTRAINT entities_id_kind_key UNIQUE (id, kind);

CREATE TABLE public.chunk_entity_references (
    chunk_id bigint NOT NULL,
    entity_id bigint NOT NULL,
    entity_kind public.entity_kind NOT NULL,
    reference_kind public.chunk_reference_kind,
    evidence text,
    CONSTRAINT chunk_entity_references_chunk_id_fkey
        FOREIGN KEY (chunk_id) REFERENCES public.narrative_chunks(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chunk_entity_references_entity_fkey
        FOREIGN KEY (entity_id, entity_kind) REFERENCES public.entities(id, kind),
    CONSTRAINT chunk_entity_references_kind_check CHECK ((
        CASE entity_kind
            WHEN 'character' THEN evidence IS NULL
                AND (reference_kind IS NULL
                     OR reference_kind IN ('present', 'mentioned'))
            WHEN 'faction' THEN evidence IS NULL
                AND reference_kind = 'mentioned'
            WHEN 'place' THEN reference_kind IN ('setting', 'mentioned', 'transit')
        END
    ) IS TRUE)
);

CREATE UNIQUE INDEX chunk_entity_references_single_role_key
    ON public.chunk_entity_references (chunk_id, entity_id)
    WHERE entity_kind IN ('character', 'faction');

CREATE UNIQUE INDEX chunk_entity_references_place_role_key
    ON public.chunk_entity_references (chunk_id, entity_id, reference_kind)
    WHERE entity_kind = 'place';

CREATE INDEX chunk_entity_references_entity_idx
    ON public.chunk_entity_references (entity_id);

CREATE FUNCTION public.chunk_entity_references_forget_subtype()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- The entity stays: subtype rows reference entities with no delete
    -- action, and only the subtype's chunk references go.
    DELETE FROM public.chunk_entity_references WHERE entity_id = OLD.entity_id;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_characters_forget_chunk_references
    AFTER DELETE ON public.characters
    FOR EACH ROW EXECUTE FUNCTION public.chunk_entity_references_forget_subtype();

CREATE TRIGGER trg_factions_forget_chunk_references
    AFTER DELETE ON public.factions
    FOR EACH ROW EXECUTE FUNCTION public.chunk_entity_references_forget_subtype();

CREATE TRIGGER trg_places_forget_chunk_references
    AFTER DELETE ON public.places
    FOR EACH ROW EXECUTE FUNCTION public.chunk_entity_references_forget_subtype();

CREATE FUNCTION public.chunk_character_references_mirror()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    subtype_entity_id bigint;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT c.entity_id INTO subtype_entity_id
          FROM public.characters AS c
         WHERE c.id = OLD.character_id;
        IF FOUND THEN
            DELETE FROM public.chunk_entity_references
             WHERE chunk_id = OLD.chunk_id
               AND entity_id = subtype_entity_id
               AND entity_kind = 'character';
        END IF;
        -- Not found: the characters row is being deleted (its forget trigger
        -- removes the rows) or renumbered by ON UPDATE CASCADE (its entity,
        -- and so its unified row, is unchanged). Nothing to do here.
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT c.entity_id INTO subtype_entity_id
          FROM public.characters AS c
         WHERE c.id = NEW.character_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'chunk_character_references names character_id %, which has no characters row',
                NEW.character_id;
        END IF;
        INSERT INTO public.chunk_entity_references
            (chunk_id, entity_id, entity_kind, reference_kind, evidence)
        VALUES (
            NEW.chunk_id, subtype_entity_id, 'character',
            NEW.reference::text::public.chunk_reference_kind, NULL
        )
        ON CONFLICT (chunk_id, entity_id)
            WHERE entity_kind IN ('character', 'faction')
        DO UPDATE SET reference_kind = EXCLUDED.reference_kind;
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION public.chunk_faction_references_mirror()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    subtype_entity_id bigint;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT f.entity_id INTO subtype_entity_id
          FROM public.factions AS f
         WHERE f.id = OLD.faction_id;
        IF FOUND THEN
            DELETE FROM public.chunk_entity_references
             WHERE chunk_id = OLD.chunk_id
               AND entity_id = subtype_entity_id
               AND entity_kind = 'faction';
        END IF;
        -- Not found: the factions row is being deleted (its forget trigger
        -- removes the rows) or renumbered by ON UPDATE CASCADE (its entity,
        -- and so its unified row, is unchanged). Nothing to do here.
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT f.entity_id INTO subtype_entity_id
          FROM public.factions AS f
         WHERE f.id = NEW.faction_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'chunk_faction_references names faction_id %, which has no factions row',
                NEW.faction_id;
        END IF;
        INSERT INTO public.chunk_entity_references
            (chunk_id, entity_id, entity_kind, reference_kind, evidence)
        VALUES (NEW.chunk_id, subtype_entity_id, 'faction', 'mentioned', NULL)
        ON CONFLICT (chunk_id, entity_id)
            WHERE entity_kind IN ('character', 'faction')
        DO NOTHING;
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION public.place_chunk_references_mirror()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    subtype_entity_id bigint;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT p.entity_id INTO subtype_entity_id
          FROM public.places AS p
         WHERE p.id = OLD.place_id;
        IF FOUND THEN
            DELETE FROM public.chunk_entity_references
             WHERE chunk_id = OLD.chunk_id
               AND entity_id = subtype_entity_id
               AND entity_kind = 'place'
               AND reference_kind = OLD.reference_type::text::public.chunk_reference_kind;
        END IF;
        -- Not found: the places row is being deleted (its forget trigger
        -- removes the rows) or renumbered by ON UPDATE CASCADE (its entity,
        -- and so its unified row, is unchanged). Nothing to do here.
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT p.entity_id INTO subtype_entity_id
          FROM public.places AS p
         WHERE p.id = NEW.place_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION
                'place_chunk_references names place_id %, which has no places row',
                NEW.place_id;
        END IF;
        INSERT INTO public.chunk_entity_references
            (chunk_id, entity_id, entity_kind, reference_kind, evidence)
        VALUES (
            NEW.chunk_id, subtype_entity_id, 'place',
            NEW.reference_type::text::public.chunk_reference_kind, NEW.evidence
        )
        ON CONFLICT (chunk_id, entity_id, reference_kind)
            WHERE entity_kind = 'place'
        DO UPDATE SET evidence = EXCLUDED.evidence;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_chunk_character_references_mirror
    AFTER INSERT OR UPDATE OR DELETE ON public.chunk_character_references
    FOR EACH ROW EXECUTE FUNCTION public.chunk_character_references_mirror();

CREATE TRIGGER trg_chunk_faction_references_mirror
    AFTER INSERT OR UPDATE OR DELETE ON public.chunk_faction_references
    FOR EACH ROW EXECUTE FUNCTION public.chunk_faction_references_mirror();

CREATE TRIGGER trg_place_chunk_references_mirror
    AFTER INSERT OR UPDATE OR DELETE ON public.place_chunk_references
    FOR EACH ROW EXECUTE FUNCTION public.place_chunk_references_mirror();

INSERT INTO public.chunk_entity_references
    (chunk_id, entity_id, entity_kind, reference_kind, evidence)
SELECT r.chunk_id, c.entity_id, 'character'::public.entity_kind,
       r.reference::text::public.chunk_reference_kind, NULL::text
  FROM public.chunk_character_references AS r
  JOIN public.characters AS c ON c.id = r.character_id
UNION ALL
SELECT r.chunk_id, f.entity_id, 'faction', 'mentioned', NULL
  FROM public.chunk_faction_references AS r
  JOIN public.factions AS f ON f.id = r.faction_id
UNION ALL
SELECT r.chunk_id, p.entity_id, 'place',
       r.reference_type::text::public.chunk_reference_kind, r.evidence
  FROM public.place_chunk_references AS r
  JOIN public.places AS p ON p.id = r.place_id;

DO $m148$
DECLARE
    kind_name public.entity_kind;
    expected_count bigint;
    actual_count bigint;
    missing_example text;
    extra_example text;
BEGIN
    FOREACH kind_name IN ARRAY enum_range(NULL::public.entity_kind) LOOP
        WITH expected AS (
            SELECT r.chunk_id, c.entity_id,
                   'character'::public.entity_kind AS entity_kind,
                   r.reference::text::public.chunk_reference_kind AS reference_kind,
                   NULL::text AS evidence
              FROM public.chunk_character_references AS r
              JOIN public.characters AS c ON c.id = r.character_id
            UNION ALL
            SELECT r.chunk_id, f.entity_id, 'faction', 'mentioned', NULL
              FROM public.chunk_faction_references AS r
              JOIN public.factions AS f ON f.id = r.faction_id
            UNION ALL
            SELECT r.chunk_id, p.entity_id, 'place',
                   r.reference_type::text::public.chunk_reference_kind, r.evidence
              FROM public.place_chunk_references AS r
              JOIN public.places AS p ON p.id = r.place_id
        ),
        expected_kind AS (
            SELECT * FROM expected WHERE entity_kind = kind_name
        ),
        actual_kind AS (
            SELECT chunk_id, entity_id, entity_kind, reference_kind, evidence
              FROM public.chunk_entity_references
             WHERE entity_kind = kind_name
        )
        SELECT (SELECT count(*) FROM expected_kind),
               (SELECT count(*) FROM actual_kind),
               (SELECT m::text FROM (
                    SELECT * FROM expected_kind
                    EXCEPT ALL
                    SELECT * FROM actual_kind
                ) AS m LIMIT 1),
               (SELECT x::text FROM (
                    SELECT * FROM actual_kind
                    EXCEPT ALL
                    SELECT * FROM expected_kind
                ) AS x LIMIT 1)
          INTO expected_count, actual_count, missing_example, extra_example;
        IF expected_count <> actual_count
           OR missing_example IS NOT NULL
           OR extra_example IS NOT NULL THEN
            RAISE EXCEPTION
                'Migration 148: % rows of chunk_entity_references differ from their junction: expected % rows, found %; a missing row: %; an extra row: %',
                kind_name, expected_count, actual_count,
                COALESCE(missing_example, 'none'), COALESCE(extra_example, 'none');
        END IF;
    END LOOP;
END
$m148$;

COMMENT ON TYPE public.chunk_reference_kind IS
    'Role of a chunk reference in chunk_entity_references: present or mentioned for a character, mentioned for a faction, setting, mentioned or transit for a place. chunk_entity_references_kind_check enforces the roles per entity kind.';

COMMENT ON TABLE public.chunk_entity_references IS
    'One row per reference of a chunk to a character, faction or place, keyed by entities.id. During #836''s transition it mirrors the three junctions (chunk_character_references, chunk_faction_references, place_chunk_references) through their row triggers, and the junctions stay authoritative until they are retired. Character and faction rows are unique per (chunk_id, entity_id) and place rows per (chunk_id, entity_id, reference_kind), so one place can hold several roles in one chunk. Nothing limits a chunk to one setting place. Deleting a character, faction or place row deletes its rows here and keeps the entity.';

COMMENT ON COLUMN public.chunk_entity_references.chunk_id IS
    'The referencing chunk, narrative_chunks.id. Deleting or renumbering the chunk deletes or renumbers its rows here.';

COMMENT ON COLUMN public.chunk_entity_references.entity_id IS
    'The referenced character, faction or place, entities.id (the subtype row''s entity_id, not its subtype id).';

COMMENT ON COLUMN public.chunk_entity_references.entity_kind IS
    'entities.kind of entity_id, carried here so the per-kind check and the per-kind unique indexes can read it; chunk_entity_references_entity_fkey keeps it equal to entities.kind.';

COMMENT ON COLUMN public.chunk_entity_references.reference_kind IS
    'Role of the reference. Character rows: present or mentioned, or NULL, as chunk_character_references.reference may be. Faction rows: mentioned, because their junction has no role column. Place rows: setting, mentioned or transit, never NULL.';

COMMENT ON COLUMN public.chunk_entity_references.evidence IS
    'place_chunk_references.evidence for a place row, and may be NULL there. NULL on every character and faction row.';

COMMENT ON CONSTRAINT chunk_entity_references_chunk_id_fkey
    ON public.chunk_entity_references IS
    'Each row names an existing narrative_chunks row; it follows the chunk on update and is deleted with it, as the junctions are.';

COMMENT ON CONSTRAINT chunk_entity_references_entity_fkey
    ON public.chunk_entity_references IS
    'Each row names an existing entity of the stated kind. No action clause: an entity''s kind cannot change, and the entity cannot be deleted, while a row names it.';

COMMENT ON CONSTRAINT chunk_entity_references_kind_check
    ON public.chunk_entity_references IS
    'Roles per entity kind: a character row has no evidence and a NULL, present or mentioned role; a faction row has no evidence and the role mentioned; a place row has the role setting, mentioned or transit. A NULL result is a violation, so a place row needs a role.';

COMMENT ON CONSTRAINT entities_id_kind_key ON public.entities IS
    'Unique (id, kind), the target of chunk_entity_references_entity_fkey, so a reference row can state its entity''s kind and have it checked.';

COMMENT ON INDEX public.chunk_entity_references_single_role_key IS
    'One character or faction row per (chunk_id, entity_id), as the character and faction junctions'' primary keys allow; the conflict target of their mirror triggers.';

COMMENT ON INDEX public.chunk_entity_references_place_role_key IS
    'One place row per (chunk_id, entity_id, reference_kind), as place_chunk_references''s primary key allows, so one place can hold several roles in one chunk; the conflict target of its mirror trigger.';

COMMENT ON INDEX public.chunk_entity_references_entity_idx IS
    'Finds every chunk reference to one entity, for readers and for chunk_entity_references_forget_subtype().';

COMMENT ON FUNCTION public.chunk_entity_references_forget_subtype() IS
    'Trigger function on characters, factions and places: after a subtype row is deleted, deletes the chunk_entity_references rows that name its entity_id. The entity row stays.';

COMMENT ON FUNCTION public.chunk_character_references_mirror() IS
    'Mirrors each chunk_character_references insert, update and delete into chunk_entity_references until the junction is retired (#836). An insert or update upserts the character row by (chunk_id, entity_id) and raises when the characters row is missing; an update or delete first removes the old row unless the old characters row no longer exists (being deleted, or renumbered by ON UPDATE CASCADE).';

COMMENT ON FUNCTION public.chunk_faction_references_mirror() IS
    'Mirrors each chunk_faction_references insert, update and delete into chunk_entity_references until the junction is retired (#836). An insert or update adds the faction row with role mentioned by (chunk_id, entity_id) and raises when the factions row is missing; an update or delete first removes the old row unless the old factions row no longer exists (being deleted, or renumbered by ON UPDATE CASCADE).';

COMMENT ON FUNCTION public.place_chunk_references_mirror() IS
    'Mirrors each place_chunk_references insert, update and delete into chunk_entity_references until the junction is retired (#836). An insert or update upserts the place row by (chunk_id, entity_id, reference_kind) with its evidence and raises when the places row is missing; an update or delete first removes the old role''s row unless the old places row no longer exists (being deleted, or renumbered by ON UPDATE CASCADE).';

COMMENT ON TRIGGER trg_characters_forget_chunk_references ON public.characters IS
    'After a characters row is deleted, deletes its chunk_entity_references rows; the entity stays.';

COMMENT ON TRIGGER trg_factions_forget_chunk_references ON public.factions IS
    'After a factions row is deleted, deletes its chunk_entity_references rows; the entity stays.';

COMMENT ON TRIGGER trg_places_forget_chunk_references ON public.places IS
    'After a places row is deleted, deletes its chunk_entity_references rows; the entity stays.';

COMMENT ON TRIGGER trg_chunk_character_references_mirror
    ON public.chunk_character_references IS
    'Mirrors every row write of this junction into chunk_entity_references until the junction is retired (#836).';

COMMENT ON TRIGGER trg_chunk_faction_references_mirror
    ON public.chunk_faction_references IS
    'Mirrors every row write of this junction into chunk_entity_references until the junction is retired (#836).';

COMMENT ON TRIGGER trg_place_chunk_references_mirror
    ON public.place_chunk_references IS
    'Mirrors every row write of this junction into chunk_entity_references until the junction is retired (#836).';
