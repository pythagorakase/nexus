-- Migration 139: Widen character_relationships Ids to bigint (issue #836)
--
-- Slice S2 of #836 (decision 836-Q1: ships now, one SQL migration through
-- scripts/migrate.py). character_relationships.character1_id and
-- character2_id are integer, but both reference characters(id), which is
-- bigint with a bigint sequence (characters_id_seq). They are the only
-- integer foreign-key columns that reference characters(id); the other
-- eight (assets.character_images, character_aliases, character_psychology,
-- chunk_character_references, faction_character_relationships,
-- global_variables.user_character, items.owner_id,
-- character_identity_rulings) are bigint, and faction_relationships and
-- faction_character_relationships are bigint on both ends. So a character
-- whose id is above 2147483647 can never hold a relationship row
-- ("integer out of range"). This migration changes the id type only, never
-- an id value or relationship_versions.old_row (836-Q3 is a later slice).
--
-- Catalog evidence, read-only on NEXUS_template and save_01..save_05 (all
-- six at migration 138) on 2026-09-30, code at 41783c1d:
--   format_type of character1_id and character2_id: integer on all six;
--   characters.id and characters_id_seq: bigint.
--   pg_depend (pg_rewrite rules): character_relationship_pairs and
--   entity_relationships_v read character_relationships;
--   character_relationship_summary reads only character_relationship_pairs.
--   Nothing else depends on the three views, and no foreign key references
--   character_relationships. PostgreSQL refuses ALTER COLUMN ... TYPE on a
--   column a view uses, so the three views are dropped and recreated here.
--   md5(pg_get_viewdef(view, true)), identical on all six databases:
--     character_relationship_pairs   b6a065311f82626698e5231b3b47b7bc
--     character_relationship_summary 5377171baacbe9e70f04f984ebc37972
--     entity_relationships_v         c09dd8617c1e293b96ce711c1321a609
--   md5(obj_description(view, 'pg_class')), identical on all six:
--     character_relationship_pairs   7c8f9eae92a3c251388e75dfabeaaf4b
--     character_relationship_summary 3a4e2c33216a42861b66302fb93e28c0
--     entity_relationships_v         8d50c14c081bbfc2f8bd8d9499af393f
--   relacl is NULL on all three views; the owner is pythagor.
--
-- The views:
--   entity_relationships_v: last defined by
--   migrations/088_valence_float_canonical.sql:151-198, column comments on
--   valence_magnitude and valence_current at :200-206, view comment by
--   migrations/137_view_comments.sql:41-42. Its id columns come from
--   characters.entity_id and are already bigint. Readers:
--   nexus/agents/orrery/resolver.py:404,656,1024;
--   nexus/agents/orrery/reveal.py:425 (_TRUST_SQL, :423);
--   nexus/agents/orrery/knowledge_surfacing.py:675;
--   nexus/agents/orrery/audit.py:2171.
--   character_relationship_pairs and character_relationship_summary: no
--   migration creates them and no SQL names them; a fresh slot gets them
--   from the template dump. git grep -n -i -P
--   "(from|join|view)\s+(public\.)?character_relationship_(pairs|summary)\b"
--   finds nothing; outside docs/qa, "character_relationship_(pairs|summary)"
--   finds only the Python names _load_character_relationship_pairs and
--   character_relationship_pairs() (nexus/agents/orrery/resolver.py:1011,
--   1211, 1270-1275, 1546-1548; quoted at migrations/137_view_comments.sql:31),
--   which read entity_relationships_v at resolver.py:1024. Their char_id_1
--   and char_id_2 columns follow the table and become bigint.
--
-- Each body below is copied verbatim from pg_get_viewdef('public.<view>'
-- ::regclass, true) on NEXUS_template (read-only session), not from
-- migration 088, and each comment byte for byte from obj_description and
-- col_description. A snapshot taken before the drop is compared with the
-- recreated views by the final DO block: definition, view comment, ACL,
-- owner, and column comments must be unchanged, or the migration raises and
-- the runner rolls the whole file back. DROP VIEW uses neither CASCADE nor
-- IF EXISTS, so an unknown dependent or a missing view also fails the file.
-- Nothing is granted: the views have no ACL today.
--
-- The table keeps character_relationships_pkey, character_relationships_check
-- (character1_id <> character2_id),
-- character_relationships_valence_current_open_check, its two foreign keys,
-- its three secondary indexes, and its two triggers
-- (trg_character_relationships_valence_boundary and
-- trg_version_character_relationships, migrations/
-- 115_relationship_write_provenance.sql:88-91); ALTER COLUMN ... TYPE
-- rebuilds the indexes and rechecks the constraints, and fires no row
-- trigger, so fn_version_relationship_row (:52-85, which reads
-- nexus.write_producer at :56 and writes to_jsonb(NEW|OLD) at :76) writes no
-- relationship_versions row. The two column comments are kept by the type
-- change. The runner executes this file as one transaction after
-- SET LOCAL nexus.write_producer = 'migration' (scripts/migrate.py:330-335).
--
-- Locks: ALTER TABLE ... TYPE rewrites character_relationships under an
-- ACCESS EXCLUSIVE lock, and DROP VIEW takes ACCESS EXCLUSIVE on each view,
-- until the transaction commits. The type change also drops and re-creates
-- the two foreign keys to characters(id); removing and re-adding their RI
-- triggers takes ACCESS EXCLUSIVE on public.characters until commit as well
-- (characters is not rewritten). The table holds at most 84 rows on the
-- fleet (save_01 and save_02), so the rewrite lasts milliseconds once the
-- locks are granted; the migration waits for any open transaction that
-- touched characters, character_relationships or the three views, and while
-- it waits in the lock queue it blocks every new reader of characters. The
-- lock_timeout below bounds each lock request, not the transaction: a run that
-- meets an open transaction waits up to five seconds, new readers queue behind
-- it for that long, and then the run fails, the queue drains, and the run is
-- repeated later (as migration 138 does). Apply it with no turn in flight and
-- no idle-in-transaction session on characters.

SET LOCAL lock_timeout = '5s';

CREATE TEMP TABLE m139_view_snapshot ON COMMIT DROP AS
SELECT c.relname::text AS relname,
       pg_get_viewdef(c.oid, true) AS definition,
       obj_description(c.oid, 'pg_class') AS view_comment,
       c.relacl::text AS acl,
       c.relowner AS owner,
       COALESCE(
           (SELECT jsonb_object_agg(a.attname, col_description(c.oid, a.attnum))
              FROM pg_attribute AS a
             WHERE a.attrelid = c.oid
               AND a.attnum > 0
               AND NOT a.attisdropped
               AND col_description(c.oid, a.attnum) IS NOT NULL),
           '{}'::jsonb
       ) AS column_comments
  FROM pg_class AS c
 WHERE c.oid IN (
           'public.character_relationship_pairs'::regclass,
           'public.character_relationship_summary'::regclass,
           'public.entity_relationships_v'::regclass
       );

DROP VIEW public.character_relationship_summary;
DROP VIEW public.character_relationship_pairs;
DROP VIEW public.entity_relationships_v;

ALTER TABLE public.character_relationships
    ALTER COLUMN character1_id TYPE bigint,
    ALTER COLUMN character2_id TYPE bigint;

CREATE VIEW public.character_relationship_pairs AS
 WITH relationship_data AS (
         SELECT LEAST(cr1.character1_id, cr1.character2_id) AS char_id_1,
            GREATEST(cr1.character1_id, cr1.character2_id) AS char_id_2,
            c1_min.name AS char_name_1,
            c2_max.name AS char_name_2,
            cr1.relationship_type AS type_1_to_2,
            cr1.emotional_valence AS valence_1_to_2,
            cr1.dynamic AS dynamic_1_to_2,
            cr1.recent_events AS recent_1_to_2,
            cr1.history AS history_1_to_2,
            cr1.extra_data AS extra_1_to_2,
            cr2.relationship_type AS type_2_to_1,
            cr2.emotional_valence AS valence_2_to_1,
            cr2.dynamic AS dynamic_2_to_1,
            cr2.recent_events AS recent_2_to_1,
            cr2.history AS history_2_to_1,
            cr2.extra_data AS extra_2_to_1,
            cr1.created_at,
            cr1.updated_at
           FROM character_relationships cr1
             JOIN character_relationships cr2 ON cr1.character1_id = cr2.character2_id AND cr1.character2_id = cr2.character1_id
             JOIN characters c1_min ON LEAST(cr1.character1_id, cr1.character2_id) = c1_min.id
             JOIN characters c2_max ON GREATEST(cr1.character1_id, cr1.character2_id) = c2_max.id
          WHERE cr1.character1_id < cr1.character2_id
        )
 SELECT char_id_1,
    char_id_2,
    char_name_1,
    char_name_2,
    type_1_to_2,
    valence_1_to_2,
    dynamic_1_to_2,
    recent_1_to_2,
    history_1_to_2,
    extra_1_to_2,
    type_2_to_1,
    valence_2_to_1,
    dynamic_2_to_1,
    recent_2_to_1,
    history_2_to_1,
    extra_2_to_1,
    created_at,
    updated_at
   FROM relationship_data
  ORDER BY char_id_1, char_id_2;

CREATE VIEW public.character_relationship_summary AS
 SELECT char_id_1,
    char_id_2,
    char_name_1,
    char_name_2,
    type_1_to_2,
    type_2_to_1,
    valence_1_to_2,
    valence_2_to_1,
    dynamic_1_to_2,
    dynamic_2_to_1
   FROM character_relationship_pairs;

CREATE VIEW public.entity_relationships_v AS
 SELECT c1.entity_id AS source_entity_id,
    c2.entity_id AS target_entity_id,
    'character'::text AS relationship_scope,
    cr.relationship_type::text AS relationship_type,
    cr.emotional_valence::text AS valence,
    cr.dynamic,
    cr.recent_events,
    cr.history,
    cr.extra_data,
    round(cr.valence_current * 5.5)::integer AS valence_magnitude,
    cr.valence_current
   FROM character_relationships cr
     JOIN characters c1 ON c1.id = cr.character1_id
     JOIN characters c2 ON c2.id = cr.character2_id
UNION ALL
 SELECT f1.entity_id AS source_entity_id,
    f2.entity_id AS target_entity_id,
    'faction'::text AS relationship_scope,
    fr.relationship_type::text AS relationship_type,
    NULL::text AS valence,
    fr.current_status AS dynamic,
    NULL::text AS recent_events,
    fr.history,
    fr.extra_data,
    NULL::integer AS valence_magnitude,
    NULL::numeric AS valence_current
   FROM faction_relationships fr
     JOIN factions f1 ON f1.id = fr.faction1_id
     JOIN factions f2 ON f2.id = fr.faction2_id
UNION ALL
 SELECT f.entity_id AS source_entity_id,
    c.entity_id AS target_entity_id,
    'faction_character'::text AS relationship_scope,
    fcr.role::text AS relationship_type,
    NULL::text AS valence,
    fcr.current_status AS dynamic,
    NULL::text AS recent_events,
    fcr.history,
    fcr.extra_data,
    NULL::integer AS valence_magnitude,
    NULL::numeric AS valence_current
   FROM faction_character_relationships fcr
     JOIN factions f ON f.id = fcr.faction_id
     JOIN characters c ON c.id = fcr.character_id;

COMMENT ON VIEW public.character_relationship_pairs IS
    'Bidirectional view of character relationships showing both perspectives';

COMMENT ON VIEW public.character_relationship_summary IS
    'Simplified summary of character relationships focusing on key dynamics';

COMMENT ON VIEW public.entity_relationships_v IS
    'Relationship edges between entities in one shape: one row for each row of character_relationships (relationship_scope character, source character1, target character2), faction_relationships (scope faction, source faction1, target faction2), and faction_character_relationships (scope faction_character, source the faction, target the character), with both ends mapped to entity ids. relationship_type carries the character relationship type, the faction relationship type, or the member role as text; dynamic carries dynamic in character scope and current_status in the other two; valence, recent_events, valence_magnitude, and valence_current are NULL outside character scope. Every reader under nexus/ selects character scope only: the Orrery resolver (orbit distances, relationship types and trust, actor-target bindings), secret reveal (trust), knowledge surfacing (valence between characters), and the audit entity hover. The resolver faction membership loader reads faction_character_relationships directly, not this view.';

COMMENT ON COLUMN public.entity_relationships_v.valence_magnitude IS
    'Signed integer in -5..+5 derived from canonical valence_current via round(valence_current * 5.5); NULL outside character scope.';

COMMENT ON COLUMN public.entity_relationships_v.valence_current IS
    'Canonical continuous signed valence for character relationships; NULL for faction and faction_character scopes.';

DO $$
DECLARE
    snap record;
    live_oid oid;
    live_definition text;
    live_comment text;
    live_acl text;
    live_owner oid;
    live_column_comments jsonb;
BEGIN
    IF (SELECT count(*) FROM m139_view_snapshot) <> 3 THEN
        RAISE EXCEPTION 'Migration 139: the snapshot holds % views, not 3',
            (SELECT count(*) FROM m139_view_snapshot);
    END IF;

    FOR snap IN SELECT * FROM m139_view_snapshot ORDER BY relname LOOP
        live_oid := to_regclass('public.' || quote_ident(snap.relname));
        IF live_oid IS NULL THEN
            RAISE EXCEPTION 'Migration 139: view % was not recreated', snap.relname;
        END IF;

        SELECT pg_get_viewdef(c.oid, true),
               obj_description(c.oid, 'pg_class'),
               c.relacl::text,
               c.relowner,
               COALESCE(
                   (SELECT jsonb_object_agg(a.attname, col_description(c.oid, a.attnum))
                      FROM pg_attribute AS a
                     WHERE a.attrelid = c.oid
                       AND a.attnum > 0
                       AND NOT a.attisdropped
                       AND col_description(c.oid, a.attnum) IS NOT NULL),
                   '{}'::jsonb
               )
          INTO live_definition, live_comment, live_acl, live_owner,
               live_column_comments
          FROM pg_class AS c
         WHERE c.oid = live_oid;

        IF live_definition IS DISTINCT FROM snap.definition THEN
            RAISE EXCEPTION
                'Migration 139: view % definition differs from the one it replaced',
                snap.relname;
        END IF;
        IF live_comment IS DISTINCT FROM snap.view_comment THEN
            RAISE EXCEPTION
                'Migration 139: view % comment differs from the one it replaced',
                snap.relname;
        END IF;
        IF live_acl IS DISTINCT FROM snap.acl THEN
            RAISE EXCEPTION
                'Migration 139: view % ACL is %, not %',
                snap.relname, coalesce(live_acl, 'NULL'), coalesce(snap.acl, 'NULL');
        END IF;
        IF live_owner IS DISTINCT FROM snap.owner THEN
            RAISE EXCEPTION
                'Migration 139: view % owner is %, not %',
                snap.relname, pg_get_userbyid(live_owner), pg_get_userbyid(snap.owner);
        END IF;
        IF live_column_comments IS DISTINCT FROM snap.column_comments THEN
            RAISE EXCEPTION
                'Migration 139: view % column comments differ from the ones it replaced',
                snap.relname;
        END IF;
    END LOOP;
END $$;
