-- Migration 147: Natural Earth Reference Table (issue #840, slice S1)
--
-- Decision 840-Q1 (per-slot public table, vendored files) and Decision
-- 840-Q2 (10m land, admin-0, admin-1), under the owner's ruling of Arachne
-- Sequence 39 (geometry dataset: Natural Earth). This migration creates the
-- empty table only; scripts/load_natural_earth.py fills it from the zips
-- vendored under data/natural_earth/ and checked against
-- data/natural_earth/manifest.json.
--
-- Evidence, read-only on NEXUS_template and save_01..save_05 (all six at
-- migration 143) on 2026-10-07, code at 364fef4b:
--   to_regclass('public.natural_earth_features') is NULL on all six, and the
--   template's geometry_columns lists only the route graph, travel edges,
--   places.geom and zones.boundary: no table in public, assets or ir_eval
--   holds land or administrative polygons. The only Natural Earth data is
--   the UI's unversioned 110m continent outline
--   (ui/client/src/lib/world-outline.ts:1-2; docs/maptab_rebuild_spec.md:478-480).
--   Genesis zones are synthetic circles of [wizard.geo] default_zone_radius_m
--   (nexus.toml:200-206; WizardGeoSettings,
--   nexus/config/settings_models.py:3831-3850); resolve_zone_for_point
--   resolves by ST_Covers on zones.boundary, geometry(MultiPolygon,4326)
--   (nexus/agents/orrery/geo.py:10-26,47-65). The table below uses the same
--   type so later zone derivation (840-S3c) can clip against it directly.
--   Fresh slots get schema from public and assets only
--   (scripts/new_story_setup.py:255) and rows only from TEMPLATE_SEED_TABLES
--   (:358-370, copied by _copy_template_data, :373-397), so the table lives
--   in public and joins TEMPLATE_SEED_TABLES in the same branch. The route
--   graph is the precedent for a per-slot table filled by a separate loader
--   (migrations/035_orrery_osm_route_graph.py;
--   scripts/import_orrery_route_graph.py:37-162).
--   PostgreSQL 17.11; PostGIS library 3.5.6 (extension 3.5.3 on
--   NEXUS_template and save_01, 3.5.6 on save_02..save_05). Every fleet
--   database already has PostGIS, so no CREATE EXTENSION.
--
-- The pinned release is Natural Earth 5.1.1 (each zip's VERSION.txt), 10m:
-- land 11 features, admin_0 258, admin_1 4,596. Exactly two published
-- features are invalid under ST_IsValid, and the loader repairs only those
-- with ST_Multi(ST_CollectionExtract(ST_MakeValid(geom, 'method=structure'),
-- 3)): admin_0 ne_id 1159320575 (EGY, Ring Self-intersection) and admin_1
-- ne_id 1159309897 (BRA-1294, Goias, Ring Self-intersection). The table has
-- no ST_IsValid CHECK: the loader proves validity once per load, and every
-- fresh-slot copy would otherwise re-validate about 2.3 million vertices.
--
-- Locks: CREATE TABLE and the CREATE INDEX statements on the new, empty
-- table lock no existing table. The lock_timeout below matches migrations
-- 138 and 139: it bounds each lock request, not the transaction, so a run
-- that cannot get a lock within five seconds fails, rolls back, and is
-- repeated later.

SET LOCAL lock_timeout = '5s';

CREATE TABLE public.natural_earth_features (
    layer text NOT NULL CHECK (layer IN ('land', 'admin_0', 'admin_1')),
    source_index integer NOT NULL CHECK (source_index >= 0),
    release text NOT NULL,
    ne_id bigint,
    adm0_a3 text,
    adm1_code text,
    iso_code text,
    name text,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (layer, source_index),
    CHECK ((layer = 'land') = (ne_id IS NULL)),
    CHECK (layer <> 'admin_0' OR (adm0_a3 IS NOT NULL AND name IS NOT NULL)),
    CHECK (layer <> 'admin_1' OR (adm0_a3 IS NOT NULL AND adm1_code IS NOT NULL))
);

CREATE INDEX natural_earth_features_geom_idx
    ON public.natural_earth_features USING gist (geom);
CREATE UNIQUE INDEX natural_earth_features_layer_ne_id_key
    ON public.natural_earth_features (layer, ne_id)
    WHERE ne_id IS NOT NULL;
CREATE INDEX natural_earth_features_layer_name_idx
    ON public.natural_earth_features (layer, lower(name));

COMMENT ON TABLE public.natural_earth_features IS 'Pinned Natural Earth 10m reference geometry (issue #840): land, admin_0 and admin_1 features of the release named in data/natural_earth/manifest.json, written only by scripts/load_natural_earth.py and copied into fresh slots as a TEMPLATE_SEED_TABLES seed table. The loader repairs exactly two published invalid features with ST_MakeValid method=structure: admin_0 ne_id 1159320575 (EGY) and admin_1 ne_id 1159309897 (BRA-1294). Read through nexus/agents/orrery/geo_reference.py.';
COMMENT ON COLUMN public.natural_earth_features.layer IS 'Natural Earth layer: land (ne_10m_land), admin_0 (ne_10m_admin_0_countries) or admin_1 (ne_10m_admin_1_states_provinces).';
COMMENT ON COLUMN public.natural_earth_features.source_index IS 'Zero-based position of the feature in its layer as ogr2ogr reads the vendored shapefile; with layer, the row identity.';
COMMENT ON COLUMN public.natural_earth_features.release IS 'Natural Earth release the row was loaded from (the manifest release, equal to each zip VERSION.txt); geo_reference.require_reference refuses rows at another release.';
COMMENT ON COLUMN public.natural_earth_features.ne_id IS 'Natural Earth feature id (NE_ID on admin_0, ne_id on admin_1); NULL exactly on land rows, which carry none. Unique per layer.';
COMMENT ON COLUMN public.natural_earth_features.adm0_a3 IS 'Natural Earth ADM0_A3 country code (admin_0 ADM0_A3, admin_1 adm0_a3); NULL on land rows.';
COMMENT ON COLUMN public.natural_earth_features.adm1_code IS 'Natural Earth adm1_code of an admin_1 region (for example USA-3522); NULL on land and admin_0 rows.';
COMMENT ON COLUMN public.natural_earth_features.iso_code IS 'ISO code from the source (admin_0 ISO_A3, admin_1 iso_3166_2); NULL on land rows and where the source holds the placeholder -99.';
COMMENT ON COLUMN public.natural_earth_features.name IS 'Source feature name (admin_0 NAME, admin_1 name); not unique, NULL on land rows and on seven admin_1 rows; lookup_region matches it case-insensitively.';
COMMENT ON COLUMN public.natural_earth_features.geom IS 'Feature geometry as a valid WGS 84 MultiPolygon; the loader proves every row valid after repairing the manifest repairs.';
