-- Migration 151: Entity IDs on Relationship Tables (issue #836)
--
-- Decision 836-Q3 maps the six subtype keys to entities once, preserving the
-- original relationship rows and every existing ledger key/value. The mapping
-- must be sound: refuse missing or reused subtype identities before any DDL.
-- fn_version_relationship_row records NEW for INSERT and OLD otherwise
-- (migrations/115_relationship_write_provenance.sql:52-85). The runner supplies
-- producer migration (scripts/migrate.py:334), so ordinary backfill UPDATEs
-- would otherwise add ledger rows. The wizard reset clears relationship and
-- subtype rows and restarts character IDs without clearing this ledger
-- (nexus/api/new_story_db_mapper.py:577-592). created_at detects reused keys,
-- including DELETE/recreation within one transaction where now() is constant.
-- Checkpoints retain whole rows (nexus/agents/orrery/reconstruction.py:115-126);
-- replay treats absent new entity columns as unknown, not historical NULL.
--
-- Historical read-only fleet survey, 2026-10-07 at migration143: character
-- relationships numbered84/84/11/15/0 across save_01..save_05 (NEXUS_template: 0);
-- faction tables were empty. Ledger counts were84/84/176/215/0 (NEXUS_template: 0),
-- all updates under unattributed_pre_115, with sound subtype creation times.
-- save_03/save_04 each had checkpoints1 and28; replay reported no drift and
--106 skipped columns. Current fleet and disposable parity are landing evidence,
-- not assertions made from those historical counts.
--
-- Locks: ADD COLUMN and ADD CONSTRAINT hold ACCESS EXCLUSIVE on the three
-- relationship tables, characters and factions until commit. The historical
-- survey bounded backfill at84 rows and ledger rewrite at215 rows per database;
-- recheck before landing. lock_timeout5s bounds each lock request, not the whole
-- transaction. Apply when no turn is in flight or relevant idle transaction
-- holds a lock. Only the three version triggers are disabled during backfill;
-- an exception rolls back schema, data, trigger state and the runner's stamp.

SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    stale_count bigint;
    first_stale jsonb;
BEGIN
    WITH key_map(relationship_table, subtype_key, subtype_table) AS (
        VALUES
            ('character_relationships', 'character1_id', 'characters'),
            ('character_relationships', 'character2_id', 'characters'),
            ('faction_relationships', 'faction1_id', 'factions'),
            ('faction_relationships', 'faction2_id', 'factions'),
            ('faction_character_relationships', 'faction_id', 'factions'),
            ('faction_character_relationships', 'character_id', 'characters')
    ), subtypes AS (
        SELECT 'characters'::text AS subtype_table, id, created_at FROM public.characters
        UNION ALL
        SELECT 'factions'::text, id, created_at FROM public.factions
    ), inspected AS (
        SELECT v.id, v.relationship_table, k.subtype_key,
               v.old_row ->> k.subtype_key AS subtype_id,
               CASE
                   WHEN v.old_row ->> k.subtype_key IS NULL THEN 'key absent or NULL'
                   WHEN s.id IS NULL THEN 'no subtype row'
                   WHEN s.created_at > v.created_at THEN 'subtype row created later'
                   WHEN v.operation = 'delete' AND s.created_at = v.created_at
                       THEN 'deleted and re-created in one transaction'
               END AS reason
        FROM public.relationship_versions v
        JOIN key_map k ON k.relationship_table = v.relationship_table
        LEFT JOIN subtypes s ON s.subtype_table = k.subtype_table
            AND s.id = (v.old_row ->> k.subtype_key)::bigint
    )
    SELECT count(DISTINCT id),
           (jsonb_agg(jsonb_build_object(
               'id', id, 'table', relationship_table, 'key', subtype_key,
               'value', subtype_id, 'reason', reason
           ) ORDER BY id, subtype_key))->0
    INTO stale_count, first_stale
    FROM inspected WHERE reason IS NOT NULL;
    IF stale_count > 0 THEN
        RAISE EXCEPTION 'Migration 151: % relationship_versions row(s) carry a stale subtype key (first: id %, table %, key % = %, reason %); refusing to map them to entity ids',
            stale_count, first_stale->>'id', first_stale->>'table',
            first_stale->>'key', first_stale->>'value', first_stale->>'reason';
    END IF;
END;
$$;

CREATE TEMP TABLE m151_versions ON COMMIT DROP AS
SELECT id, old_row FROM public.relationship_versions;

CREATE TEMP TABLE m151_rows ON COMMIT DROP AS
SELECT 'character_relationships'::text AS relationship_table, to_jsonb(r) AS "row" FROM public.character_relationships r
UNION ALL
SELECT 'faction_relationships'::text AS relationship_table, to_jsonb(r) AS "row" FROM public.faction_relationships r
UNION ALL
SELECT 'faction_character_relationships'::text AS relationship_table, to_jsonb(r) AS "row" FROM public.faction_character_relationships r;

ALTER TABLE public.characters ADD CONSTRAINT characters_id_entity_id_key UNIQUE (id, entity_id);
ALTER TABLE public.factions ADD CONSTRAINT factions_id_entity_id_key UNIQUE (id, entity_id);

ALTER TABLE public.character_relationships
    ADD COLUMN character1_entity_id bigint,
    ADD COLUMN character2_entity_id bigint;
ALTER TABLE public.faction_relationships
    ADD COLUMN faction1_entity_id bigint,
    ADD COLUMN faction2_entity_id bigint;
ALTER TABLE public.faction_character_relationships
    ADD COLUMN faction_entity_id bigint,
    ADD COLUMN character_entity_id bigint;

ALTER TABLE public.character_relationships DISABLE TRIGGER trg_version_character_relationships;
ALTER TABLE public.faction_relationships DISABLE TRIGGER trg_version_faction_relationships;
ALTER TABLE public.faction_character_relationships DISABLE TRIGGER trg_version_faction_character_relationships;

UPDATE public.character_relationships r
SET character1_entity_id = p0.entity_id, character2_entity_id = p1.entity_id
FROM public.characters p0, public.characters p1
WHERE r.character1_id = p0.id AND r.character2_id = p1.id;
UPDATE public.faction_relationships r
SET faction1_entity_id = p0.entity_id, faction2_entity_id = p1.entity_id
FROM public.factions p0, public.factions p1
WHERE r.faction1_id = p0.id AND r.faction2_id = p1.id;
UPDATE public.faction_character_relationships r
SET faction_entity_id = p0.entity_id, character_entity_id = p1.entity_id
FROM public.factions p0, public.characters p1
WHERE r.faction_id = p0.id AND r.character_id = p1.id;

ALTER TABLE public.character_relationships ENABLE TRIGGER trg_version_character_relationships;
ALTER TABLE public.faction_relationships ENABLE TRIGGER trg_version_faction_relationships;
ALTER TABLE public.faction_character_relationships ENABLE TRIGGER trg_version_faction_character_relationships;

ALTER TABLE public.character_relationships
    ALTER COLUMN character1_entity_id SET NOT NULL,
    ALTER COLUMN character2_entity_id SET NOT NULL;
ALTER TABLE public.faction_relationships
    ALTER COLUMN faction1_entity_id SET NOT NULL,
    ALTER COLUMN faction2_entity_id SET NOT NULL;
ALTER TABLE public.faction_character_relationships
    ALTER COLUMN faction_entity_id SET NOT NULL,
    ALTER COLUMN character_entity_id SET NOT NULL;
ALTER TABLE public.character_relationships
    ADD CONSTRAINT character_relationships_character1_entity_fkey
        FOREIGN KEY (character1_id, character1_entity_id) REFERENCES public.characters (id, entity_id),
    ADD CONSTRAINT character_relationships_character2_entity_fkey
        FOREIGN KEY (character2_id, character2_entity_id) REFERENCES public.characters (id, entity_id);
ALTER TABLE public.faction_relationships
    ADD CONSTRAINT faction_relationships_faction1_entity_fkey
        FOREIGN KEY (faction1_id, faction1_entity_id) REFERENCES public.factions (id, entity_id),
    ADD CONSTRAINT faction_relationships_faction2_entity_fkey
        FOREIGN KEY (faction2_id, faction2_entity_id) REFERENCES public.factions (id, entity_id);
ALTER TABLE public.faction_character_relationships
    ADD CONSTRAINT faction_character_relationships_faction_entity_fkey
        FOREIGN KEY (faction_id, faction_entity_id) REFERENCES public.factions (id, entity_id),
    ADD CONSTRAINT faction_character_relationships_character_entity_fkey
        FOREIGN KEY (character_id, character_entity_id) REFERENCES public.characters (id, entity_id);

CREATE OR REPLACE FUNCTION public.fn_relationship_entity_ids()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'character_relationships' THEN
        IF TG_OP = 'UPDATE'
           AND NEW.character1_id IS NOT DISTINCT FROM OLD.character1_id
           AND NEW.character1_entity_id IS NOT DISTINCT FROM OLD.character1_entity_id
           AND NEW.character2_id IS NOT DISTINCT FROM OLD.character2_id
           AND NEW.character2_entity_id IS NOT DISTINCT FROM OLD.character2_entity_id THEN
            RETURN NEW;
        END IF;
        IF NEW.character1_id IS NOT NULL AND (
            NEW.character1_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.character1_id IS DISTINCT FROM OLD.character1_id
                AND NEW.character1_entity_id IS NOT DISTINCT FROM OLD.character1_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.character1_entity_id
            FROM public.characters WHERE id = NEW.character1_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'character1_id', NEW.character1_id, 'characters'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'character_relationships_character1_entity_fkey';
            END IF;
        END IF;
        IF NEW.character2_id IS NOT NULL AND (
            NEW.character2_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.character2_id IS DISTINCT FROM OLD.character2_id
                AND NEW.character2_entity_id IS NOT DISTINCT FROM OLD.character2_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.character2_entity_id
            FROM public.characters WHERE id = NEW.character2_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'character2_id', NEW.character2_id, 'characters'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'character_relationships_character2_entity_fkey';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'faction_relationships' THEN
        IF TG_OP = 'UPDATE'
           AND NEW.faction1_id IS NOT DISTINCT FROM OLD.faction1_id
           AND NEW.faction1_entity_id IS NOT DISTINCT FROM OLD.faction1_entity_id
           AND NEW.faction2_id IS NOT DISTINCT FROM OLD.faction2_id
           AND NEW.faction2_entity_id IS NOT DISTINCT FROM OLD.faction2_entity_id THEN
            RETURN NEW;
        END IF;
        IF NEW.faction1_id IS NOT NULL AND (
            NEW.faction1_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.faction1_id IS DISTINCT FROM OLD.faction1_id
                AND NEW.faction1_entity_id IS NOT DISTINCT FROM OLD.faction1_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.faction1_entity_id
            FROM public.factions WHERE id = NEW.faction1_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'faction1_id', NEW.faction1_id, 'factions'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'faction_relationships_faction1_entity_fkey';
            END IF;
        END IF;
        IF NEW.faction2_id IS NOT NULL AND (
            NEW.faction2_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.faction2_id IS DISTINCT FROM OLD.faction2_id
                AND NEW.faction2_entity_id IS NOT DISTINCT FROM OLD.faction2_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.faction2_entity_id
            FROM public.factions WHERE id = NEW.faction2_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'faction2_id', NEW.faction2_id, 'factions'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'faction_relationships_faction2_entity_fkey';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'faction_character_relationships' THEN
        IF TG_OP = 'UPDATE'
           AND NEW.faction_id IS NOT DISTINCT FROM OLD.faction_id
           AND NEW.faction_entity_id IS NOT DISTINCT FROM OLD.faction_entity_id
           AND NEW.character_id IS NOT DISTINCT FROM OLD.character_id
           AND NEW.character_entity_id IS NOT DISTINCT FROM OLD.character_entity_id THEN
            RETURN NEW;
        END IF;
        IF NEW.faction_id IS NOT NULL AND (
            NEW.faction_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.faction_id IS DISTINCT FROM OLD.faction_id
                AND NEW.faction_entity_id IS NOT DISTINCT FROM OLD.faction_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.faction_entity_id
            FROM public.factions WHERE id = NEW.faction_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'faction_id', NEW.faction_id, 'factions'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'faction_character_relationships_faction_entity_fkey';
            END IF;
        END IF;
        IF NEW.character_id IS NOT NULL AND (
            NEW.character_entity_id IS NULL OR
            (TG_OP = 'UPDATE' AND NEW.character_id IS DISTINCT FROM OLD.character_id
                AND NEW.character_entity_id IS NOT DISTINCT FROM OLD.character_entity_id)
        ) THEN
            SELECT entity_id INTO NEW.character_entity_id
            FROM public.characters WHERE id = NEW.character_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION '%.% = % names no % row',
                    TG_TABLE_NAME, 'character_id', NEW.character_id, 'characters'
                    USING ERRCODE = 'foreign_key_violation',
                          CONSTRAINT = 'faction_character_relationships_character_entity_fkey';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_character_relationships_entity_ids
    BEFORE INSERT OR UPDATE ON public.character_relationships
    FOR EACH ROW EXECUTE FUNCTION public.fn_relationship_entity_ids();
CREATE TRIGGER trg_faction_relationships_entity_ids
    BEFORE INSERT OR UPDATE ON public.faction_relationships
    FOR EACH ROW EXECUTE FUNCTION public.fn_relationship_entity_ids();
CREATE TRIGGER trg_faction_character_relationships_entity_ids
    BEFORE INSERT OR UPDATE ON public.faction_character_relationships
    FOR EACH ROW EXECUTE FUNCTION public.fn_relationship_entity_ids();

UPDATE public.relationship_versions v
SET old_row = v.old_row || jsonb_build_object(
    'character1_entity_id', p0.entity_id,
    'character2_entity_id', p1.entity_id
)
FROM public.characters p0, public.characters p1
WHERE v.relationship_table = 'character_relationships'
  AND (v.old_row->>'character1_id')::bigint = p0.id
  AND (v.old_row->>'character2_id')::bigint = p1.id;

UPDATE public.relationship_versions v
SET old_row = v.old_row || jsonb_build_object(
    'faction1_entity_id', p0.entity_id,
    'faction2_entity_id', p1.entity_id
)
FROM public.factions p0, public.factions p1
WHERE v.relationship_table = 'faction_relationships'
  AND (v.old_row->>'faction1_id')::bigint = p0.id
  AND (v.old_row->>'faction2_id')::bigint = p1.id;

UPDATE public.relationship_versions v
SET old_row = v.old_row || jsonb_build_object(
    'faction_entity_id', p0.entity_id,
    'character_entity_id', p1.entity_id
)
FROM public.factions p0, public.characters p1
WHERE v.relationship_table = 'faction_character_relationships'
  AND (v.old_row->>'faction_id')::bigint = p0.id
  AND (v.old_row->>'character_id')::bigint = p1.id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.character_relationships r
        LEFT JOIN public.characters p0 ON p0.id = r.character1_id
        LEFT JOIN public.characters p1 ON p1.id = r.character2_id
        WHERE r.character1_entity_id IS DISTINCT FROM p0.entity_id OR r.character2_entity_id IS DISTINCT FROM p1.entity_id) THEN
        RAISE EXCEPTION 'Migration 151: character_relationships entity mapping differs';
    END IF;
    IF EXISTS (SELECT 1 FROM public.faction_relationships r
        LEFT JOIN public.factions p0 ON p0.id = r.faction1_id
        LEFT JOIN public.factions p1 ON p1.id = r.faction2_id
        WHERE r.faction1_entity_id IS DISTINCT FROM p0.entity_id OR r.faction2_entity_id IS DISTINCT FROM p1.entity_id) THEN
        RAISE EXCEPTION 'Migration 151: faction_relationships entity mapping differs';
    END IF;
    IF EXISTS (SELECT 1 FROM public.faction_character_relationships r
        LEFT JOIN public.factions p0 ON p0.id = r.faction_id
        LEFT JOIN public.characters p1 ON p1.id = r.character_id
        WHERE r.faction_entity_id IS DISTINCT FROM p0.entity_id OR r.character_entity_id IS DISTINCT FROM p1.entity_id) THEN
        RAISE EXCEPTION 'Migration 151: faction_character_relationships entity mapping differs';
    END IF;
    IF EXISTS (
        (SELECT relationship_table, "row" FROM m151_rows
         EXCEPT ALL
         SELECT relationship_table, "row" FROM (
SELECT 'character_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['character1_entity_id','character2_entity_id']::text[] AS "row" FROM public.character_relationships r
UNION ALL
SELECT 'faction_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['faction1_entity_id','faction2_entity_id']::text[] AS "row" FROM public.faction_relationships r
UNION ALL
SELECT 'faction_character_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['faction_entity_id','character_entity_id']::text[] AS "row" FROM public.faction_character_relationships r         ) current_rows)
        UNION ALL
        (SELECT relationship_table, "row" FROM (
SELECT 'character_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['character1_entity_id','character2_entity_id']::text[] AS "row" FROM public.character_relationships r
UNION ALL
SELECT 'faction_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['faction1_entity_id','faction2_entity_id']::text[] AS "row" FROM public.faction_relationships r
UNION ALL
SELECT 'faction_character_relationships'::text AS relationship_table, to_jsonb(r) - ARRAY['faction_entity_id','character_entity_id']::text[] AS "row" FROM public.faction_character_relationships r         ) current_rows
         EXCEPT ALL SELECT relationship_table, "row" FROM m151_rows)
    ) THEN
        RAISE EXCEPTION 'Migration 151: relationship rows changed beyond entity-id columns';
    END IF;
    IF (SELECT count(*) FROM public.relationship_versions)
        IS DISTINCT FROM (SELECT count(*) FROM m151_versions)
       OR (SELECT max(id) FROM public.relationship_versions)
        IS DISTINCT FROM (SELECT max(id) FROM m151_versions) THEN
        RAISE EXCEPTION 'Migration 151: relationship version count or max id changed';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.relationship_versions v
        JOIN m151_versions before ON before.id = v.id
        LEFT JOIN public.characters p0 ON p0.id = (v.old_row->>'character1_id')::bigint
        LEFT JOIN public.characters p1 ON p1.id = (v.old_row->>'character2_id')::bigint
        WHERE v.relationship_table = 'character_relationships'
          AND (v.old_row - ARRAY['character1_entity_id','character2_entity_id']::text[] IS DISTINCT FROM before.old_row
               OR (v.old_row->>'character1_entity_id')::bigint IS DISTINCT FROM p0.entity_id
               OR (v.old_row->>'character2_entity_id')::bigint IS DISTINCT FROM p1.entity_id
)
    ) THEN
        RAISE EXCEPTION 'Migration 151: character_relationships ledger rewrite differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.relationship_versions v
        JOIN m151_versions before ON before.id = v.id
        LEFT JOIN public.factions p0 ON p0.id = (v.old_row->>'faction1_id')::bigint
        LEFT JOIN public.factions p1 ON p1.id = (v.old_row->>'faction2_id')::bigint
        WHERE v.relationship_table = 'faction_relationships'
          AND (v.old_row - ARRAY['faction1_entity_id','faction2_entity_id']::text[] IS DISTINCT FROM before.old_row
               OR (v.old_row->>'faction1_entity_id')::bigint IS DISTINCT FROM p0.entity_id
               OR (v.old_row->>'faction2_entity_id')::bigint IS DISTINCT FROM p1.entity_id
)
    ) THEN
        RAISE EXCEPTION 'Migration 151: faction_relationships ledger rewrite differs';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.relationship_versions v
        JOIN m151_versions before ON before.id = v.id
        LEFT JOIN public.factions p0 ON p0.id = (v.old_row->>'faction_id')::bigint
        LEFT JOIN public.characters p1 ON p1.id = (v.old_row->>'character_id')::bigint
        WHERE v.relationship_table = 'faction_character_relationships'
          AND (v.old_row - ARRAY['faction_entity_id','character_entity_id']::text[] IS DISTINCT FROM before.old_row
               OR (v.old_row->>'faction_entity_id')::bigint IS DISTINCT FROM p0.entity_id
               OR (v.old_row->>'character_entity_id')::bigint IS DISTINCT FROM p1.entity_id
)
    ) THEN
        RAISE EXCEPTION 'Migration 151: faction_character_relationships ledger rewrite differs';
    END IF;
    IF (SELECT count(*) FROM pg_trigger
        WHERE (tgrelid, tgname::text) IN (
            ('public.character_relationships'::regclass, 'trg_version_character_relationships'),
            ('public.faction_relationships'::regclass, 'trg_version_faction_relationships'),
            ('public.faction_character_relationships'::regclass, 'trg_version_faction_character_relationships')        ) AND tgenabled = 'O') <> 3 THEN
        RAISE EXCEPTION 'Migration 151: relationship version triggers are not enabled';
    END IF;
END;
$$;

COMMENT ON COLUMN public.character_relationships.character1_entity_id IS 'entities.id of the row in character1_id (its characters.entity_id). trg_character_relationships_entity_ids fills it when a writer leaves it NULL, and character_relationships_character1_entity_fkey requires (character1_id, character1_entity_id) to match a characters (id, entity_id) row.';
COMMENT ON CONSTRAINT character_relationships_character1_entity_fkey ON public.character_relationships IS '(character1_id, character1_entity_id) names one characters row and that row''s entity, so character1_entity_id cannot differ from the characters row''s entity_id.';
COMMENT ON COLUMN public.character_relationships.character2_entity_id IS 'entities.id of the row in character2_id (its characters.entity_id). trg_character_relationships_entity_ids fills it when a writer leaves it NULL, and character_relationships_character2_entity_fkey requires (character2_id, character2_entity_id) to match a characters (id, entity_id) row.';
COMMENT ON CONSTRAINT character_relationships_character2_entity_fkey ON public.character_relationships IS '(character2_id, character2_entity_id) names one characters row and that row''s entity, so character2_entity_id cannot differ from the characters row''s entity_id.';
COMMENT ON COLUMN public.faction_relationships.faction1_entity_id IS 'entities.id of the row in faction1_id (its factions.entity_id). trg_faction_relationships_entity_ids fills it when a writer leaves it NULL, and faction_relationships_faction1_entity_fkey requires (faction1_id, faction1_entity_id) to match a factions (id, entity_id) row.';
COMMENT ON CONSTRAINT faction_relationships_faction1_entity_fkey ON public.faction_relationships IS '(faction1_id, faction1_entity_id) names one factions row and that row''s entity, so faction1_entity_id cannot differ from the factions row''s entity_id.';
COMMENT ON COLUMN public.faction_relationships.faction2_entity_id IS 'entities.id of the row in faction2_id (its factions.entity_id). trg_faction_relationships_entity_ids fills it when a writer leaves it NULL, and faction_relationships_faction2_entity_fkey requires (faction2_id, faction2_entity_id) to match a factions (id, entity_id) row.';
COMMENT ON CONSTRAINT faction_relationships_faction2_entity_fkey ON public.faction_relationships IS '(faction2_id, faction2_entity_id) names one factions row and that row''s entity, so faction2_entity_id cannot differ from the factions row''s entity_id.';
COMMENT ON COLUMN public.faction_character_relationships.faction_entity_id IS 'entities.id of the row in faction_id (its factions.entity_id). trg_faction_character_relationships_entity_ids fills it when a writer leaves it NULL, and faction_character_relationships_faction_entity_fkey requires (faction_id, faction_entity_id) to match a factions (id, entity_id) row.';
COMMENT ON CONSTRAINT faction_character_relationships_faction_entity_fkey ON public.faction_character_relationships IS '(faction_id, faction_entity_id) names one factions row and that row''s entity, so faction_entity_id cannot differ from the factions row''s entity_id.';
COMMENT ON COLUMN public.faction_character_relationships.character_entity_id IS 'entities.id of the row in character_id (its characters.entity_id). trg_faction_character_relationships_entity_ids fills it when a writer leaves it NULL, and faction_character_relationships_character_entity_fkey requires (character_id, character_entity_id) to match a characters (id, entity_id) row.';
COMMENT ON CONSTRAINT faction_character_relationships_character_entity_fkey ON public.faction_character_relationships IS '(character_id, character_entity_id) names one characters row and that row''s entity, so character_entity_id cannot differ from the characters row''s entity_id.';
COMMENT ON CONSTRAINT characters_id_entity_id_key ON public.characters IS 'Target of the composite foreign keys that tie each relationship entity id to its characters row; id alone is already unique.';
COMMENT ON CONSTRAINT factions_id_entity_id_key ON public.factions IS 'Target of the composite foreign keys that tie each relationship entity id to its factions row; id alone is already unique.';
COMMENT ON FUNCTION public.fn_relationship_entity_ids() IS 'BEFORE INSERT OR UPDATE trigger function on character_relationships, faction_relationships and faction_character_relationships. For each subtype id it sets the matching entity-id column to the subtype row''s entity_id when the entity id is NULL, or when an UPDATE changes the subtype id and leaves the entity id unchanged. When it derives an entity id from a subtype id that names no row, it raises foreign_key_violation under that column pair''s composite foreign key name. A supplied entity id is kept, and the composite foreign key rejects one that does not match. An UPDATE that changes no subtype id or entity id returns at once.';
COMMENT ON TRIGGER trg_character_relationships_entity_ids ON public.character_relationships IS 'Fills the entity-id columns of character_relationships through fn_relationship_entity_ids() before every INSERT and UPDATE; an UPDATE that changes no subtype id or entity id passes through unchanged.';
COMMENT ON TRIGGER trg_faction_relationships_entity_ids ON public.faction_relationships IS 'Fills the entity-id columns of faction_relationships through fn_relationship_entity_ids() before every INSERT and UPDATE; an UPDATE that changes no subtype id or entity id passes through unchanged.';
COMMENT ON TRIGGER trg_faction_character_relationships_entity_ids ON public.faction_character_relationships IS 'Fills the entity-id columns of faction_character_relationships through fn_relationship_entity_ids() before every INSERT and UPDATE; an UPDATE that changes no subtype id or entity id passes through unchanged.';
COMMENT ON COLUMN public.relationship_versions.old_row IS 'Full pre-image for UPDATE and DELETE; inserted row for INSERT so replay can remove its natural key. Every row carries both the subtype ids and the entity ids of its relationship row. Rows written before migration 151 gained the entity ids in a one-time rewrite at that migration that kept every original key and value.';
