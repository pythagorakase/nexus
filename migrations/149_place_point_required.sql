-- Migration 149: Require Authored Points for New Places (issue #840)
--
-- At 4ae8b8d2, Retrograde persistence inserts a place with the story zone and
-- no point (nexus/agents/orrery/retrograde_persistence.py:3209-3229), as does
-- the trait compiler (nexus/api/trait_compiler.py:1843-1867). Declarations
-- permit a missing point (nexus/agents/logon/apex_schema.py:170-195), and
-- maturation fills it later (retrograde_maturation.py:1575-1606).
--
-- Decisions 840-Q5 and 840-Q6: enforce points on new rows only; existing
-- pointless places and boundary-less zones stay, with no backfill. Every
-- place, including a virtual place or vehicle, carries an authored real-Earth
-- point. Unsupported points are refused, never invented.
--
-- Historical read-only survey, 2026-10-07 at migration 143: save_01/save_02
-- each had 27 of 77 places without a point, save_03 had 3 of 5, and save_04
-- had 5 of 7; NEXUS_template/save_05 had no places. A NOT VALID CHECK would
-- still reject later unrelated UPDATEs of those legacy rows. These triggers
-- instead guard new INSERTs and removal of an existing point without scanning
-- or modifying a row. Current fleet observations belong in landing evidence.
--
-- Locks: DROP TRIGGER IF EXISTS briefly takes ACCESS EXCLUSIVE on places;
-- CREATE TRIGGER takes SHARE ROW EXCLUSIVE. Neither scans a row. lock_timeout
-- is 5s; apply when no turn is in flight.

SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.places_refuse_missing_point()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'not_null_violation',
        MESSAGE = format('Place %L has no point (%s); every new place carries real-Earth coordinates and a point is never removed', NEW.name, TG_OP),
        SCHEMA = 'public',
        TABLE = 'places',
        COLUMN = 'coordinates';
END;
$$;

DROP TRIGGER IF EXISTS trg_places_require_point ON public.places;
CREATE TRIGGER trg_places_require_point
    BEFORE INSERT ON public.places
    FOR EACH ROW WHEN (NEW.coordinates IS NULL)
    EXECUTE FUNCTION public.places_refuse_missing_point();

DROP TRIGGER IF EXISTS trg_places_keep_point ON public.places;
CREATE TRIGGER trg_places_keep_point
    BEFORE UPDATE OF coordinates ON public.places
    FOR EACH ROW WHEN (OLD.coordinates IS NOT NULL AND NEW.coordinates IS NULL)
    EXECUTE FUNCTION public.places_refuse_missing_point();

COMMENT ON FUNCTION public.places_refuse_missing_point() IS 'Trigger function for trg_places_require_point and trg_places_keep_point: raises not_null_violation naming the place. Every place inserted since migration 149 carries a real-Earth point, whatever its type, and a point is never removed (#840, Decisions 840-Q5 and 840-Q6).';
COMMENT ON TRIGGER trg_places_require_point ON public.places IS 'Refuses an INSERT of a places row whose coordinates is NULL, for every place type, virtual places and vehicles included.';
COMMENT ON TRIGGER trg_places_keep_point ON public.places IS 'Refuses an UPDATE that sets a non-NULL coordinates to NULL. A row inserted before migration 149 without a point stays updatable and may gain a point.';
COMMENT ON COLUMN public.places.coordinates IS 'Real-Earth point of the place (geography PointZM, SRID 4326, longitude as x; z and m are 0). Every row inserted since migration 149 carries one, authored by the structured output that introduced the place; a point is never removed. Rows inserted earlier may be NULL and are left as they are (#840).';
