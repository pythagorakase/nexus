import { sql } from "drizzle-orm";
import {
  pgTable,
  pgSchema,
  text,
  varchar,
  bigint,
  integer,
  jsonb,
  numeric,
  timestamp,
  interval,
  primaryKey,
  customType
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Custom PostGIS types for Drizzle
const geometry = customType<{ data: string }>({
  dataType() {
    return "geometry";
  },
});

const geography = customType<{ data: string }>({
  dataType() {
    return "geography";
  },
});

// Assets schema for media and file references
export const assetsSchema = pgSchema("assets");

// Zones table
export const zones = pgTable("zones", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('zones_id_seq'::regclass)`),
  name: varchar("name", { length: 50 }).notNull(),
  summary: varchar("summary", { length: 500 }),
  boundary: geometry("boundary"),
});

// Factions table
export const factions = pgTable("factions", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  name: varchar("name", { length: 255 }).notNull(),
  summary: text("summary"),
  ideology: text("ideology"),
  history: text("history"),
  currentActivity: text("current_activity"),
  hiddenAgenda: text("hidden_agenda"),
  territory: text("territory"),
  primaryLocation: bigint("primary_location", { mode: "number" }),
  powerLevel: numeric("power_level").default('0.5'),
  resources: text("resources"),
  extraData: jsonb("extra_data"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().default(sql`now()`),
});

// Places table
export const places = pgTable("places", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('places_id_seq'::regclass)`),
  name: varchar("name", { length: 50 }).notNull(),
  type: text("type").notNull(), // place_type enum, Drizzle treats as text
  zone: bigint("zone", { mode: "number" }).notNull().references(() => zones.id),
  summary: text("summary"),
  inhabitants: text("inhabitants").array(),
  history: text("history"),
  currentStatus: text("current_status"),
  secrets: text("secrets"),
  extraData: jsonb("extra_data"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().default(sql`now()`),
  coordinates: geography("coordinates"),
  geom: geometry("geom"), // Generated column, but include for querying
});

// Characters table
export const characters = pgTable("characters", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('characters_id_seq'::regclass)`),
  name: varchar("name", { length: 50 }).notNull(),
  summary: text("summary"),
  appearance: text("appearance"),
  background: text("background").default('unknown'),
  personality: text("personality"),
  emotionalState: text("emotional_state"),
  currentActivity: text("current_activity"),
  currentLocation: text("current_location"),
  extraData: jsonb("extra_data"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().default(sql`now()`),
});

// Character relationships table
export const characterRelationships = pgTable("character_relationships", {
  character1Id: integer("character1_id").notNull().references(() => characters.id),
  character2Id: integer("character2_id").notNull().references(() => characters.id),
  relationshipType: varchar("relationship_type", { length: 50 }).notNull(),
  emotionalValence: varchar("emotional_valence", { length: 50 }).notNull(),
  dynamic: text("dynamic").notNull(),
  recentEvents: text("recent_events").notNull(),
  history: text("history").notNull(),
  extraData: jsonb("extra_data"),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`CURRENT_TIMESTAMP`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).default(sql`CURRENT_TIMESTAMP`),
});

// Character psychology table
export const characterPsychology = pgTable("character_psychology", {
  characterId: bigint("character_id", { mode: "number" }).primaryKey().references(() => characters.id),
  selfConcept: jsonb("self_concept"),
  behavior: jsonb("behavior"),
  cognitiveFramework: jsonb("cognitive_framework"),
  temperament: jsonb("temperament"),
  relationalStyle: jsonb("relational_style"),
  defenseMechanisms: jsonb("defense_mechanisms"),
  characterArc: jsonb("character_arc"),
  secrets: jsonb("secrets"),
  validationEvidence: jsonb("validation_evidence"),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).default(sql`now()`),
});

// Character images table (in assets schema)
export const characterImages = assetsSchema.table("character_images", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('assets.character_images_id_seq'::regclass)`),
  characterId: bigint("character_id", { mode: "number" }).notNull().references(() => characters.id),
  filePath: text("file_path").notNull(),
  isMain: integer("is_main").notNull().default(0), // 0 = false, 1 = true
  displayOrder: integer("display_order").notNull().default(0),
  uploadedAt: timestamp("uploaded_at", { withTimezone: true }).notNull().default(sql`now()`),
});

// Place images table (in assets schema)
export const placeImages = assetsSchema.table("place_images", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('assets.place_images_id_seq'::regclass)`),
  placeId: integer("place_id").notNull().references(() => places.id),
  filePath: text("file_path").notNull(),
  isMain: integer("is_main").notNull().default(0), // 0 = false, 1 = true
  displayOrder: integer("display_order").notNull().default(0),
  uploadedAt: timestamp("uploaded_at", { withTimezone: true }).notNull().default(sql`now()`),
});

// Seasons table
export const seasons = pgTable("seasons", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  summary: jsonb("summary"),
});

// Episodes table (composite primary key)
export const episodes = pgTable("episodes", {
  season: bigint("season", { mode: "number" }).notNull().references(() => seasons.id),
  episode: bigint("episode", { mode: "number" }).notNull(),
  chunkSpan: text("chunk_span"), // int8range stored as text
  summary: jsonb("summary"),
  tempSpan: text("temp_span"), // int8range stored as text
}, (table) => ({
  pk: primaryKey({ columns: [table.season, table.episode] })
}));

// Narrative chunks table
export const narrativeChunks = pgTable("narrative_chunks", {
  id: bigint("id", { mode: "number" }).primaryKey().default(sql`nextval('narrative_chunks_id_seq'::regclass)`),
  rawText: text("raw_text").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
});

// Chunk metadata table
export const chunkMetadata = pgTable("chunk_metadata", {
  id: bigint("id", { mode: "number" }).primaryKey(),
  chunkId: bigint("chunk_id", { mode: "number" }).notNull().references(() => narrativeChunks.id),
  season: integer("season"),
  episode: integer("episode"),
  scene: integer("scene"),
  worldLayer: text("world_layer"), // USER-DEFINED type stored as text
  timeDelta: interval("time_delta"),
  place: bigint("place", { mode: "number" }),
  metadataVersion: varchar("metadata_version", { length: 20 }),
  generationDate: timestamp("generation_date", { withTimezone: false }),
  slug: varchar("slug", { length: 10 }),
});

// Type exports
export type Zone = typeof zones.$inferSelect;
export type Faction = typeof factions.$inferSelect;

// Place type with GeoJSON geometry from PostGIS
export type Place = typeof places.$inferSelect & {
  geometry?: any | null; // GeoJSON geometry object from ST_AsGeoJSON
};

export type Character = typeof characters.$inferSelect;
export type CharacterRelationship = typeof characterRelationships.$inferSelect;
export type CharacterPsychology = typeof characterPsychology.$inferSelect;
export type CharacterImage = typeof characterImages.$inferSelect;
export type PlaceImage = typeof placeImages.$inferSelect;
export type Season = typeof seasons.$inferSelect;
export type Episode = typeof episodes.$inferSelect;
export type NarrativeChunk = typeof narrativeChunks.$inferSelect;
export type ChunkMetadata = typeof chunkMetadata.$inferSelect;
