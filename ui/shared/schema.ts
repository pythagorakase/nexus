import { sql } from "drizzle-orm";
import { 
  pgTable, 
  text, 
  varchar, 
  bigint, 
  integer,
  jsonb,
  numeric,
  timestamp,
  interval,
  primaryKey
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Users table (existing)
export const users = pgTable("users", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
});

// Zones table
export const zones = pgTable("zones", {
  id: integer("id").primaryKey().default(sql`nextval('zones_id_seq1'::regclass)`),
  name: text("name").notNull(),
  summary: text("summary"),
  boundary: jsonb("boundary"),
  worldlayerId: integer("worldlayer_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).default(sql`now()`),
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
  id: integer("id").primaryKey().default(sql`nextval('places_id_seq1'::regclass)`),
  name: text("name").notNull(),
  type: text("type"),
  description: text("description"),
  summary: text("summary"),
  latitude: numeric("latitude"),
  longitude: numeric("longitude"),
  elevation: numeric("elevation"),
  address: text("address"),
  district: text("district"),
  zoneId: integer("zone_id"),
  factionDominantId: integer("faction_dominant_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).default(sql`now()`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).default(sql`now()`),
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
  atmosphere: varchar("atmosphere", { length: 255 }),
  arcPosition: varchar("arc_position", { length: 50 }),
  direction: jsonb("direction"),
  magnitude: varchar("magnitude", { length: 50 }),
  characterElements: jsonb("character_elements"),
  perspective: jsonb("perspective"),
  interactions: jsonb("interactions"),
  dialogueAnalysis: jsonb("dialogue_analysis"),
  emotionalTone: jsonb("emotional_tone"),
  narrativeFunction: jsonb("narrative_function"),
  narrativeTechniques: jsonb("narrative_techniques"),
  thematicElements: jsonb("thematic_elements"),
  causality: jsonb("causality"),
  continuityMarkers: jsonb("continuity_markers"),
  metadataVersion: varchar("metadata_version", { length: 20 }),
  generationDate: timestamp("generation_date", { withTimezone: false }),
  slug: varchar("slug", { length: 10 }),
});

// Type exports
export type User = typeof users.$inferSelect;
export type Zone = typeof zones.$inferSelect;
export type Faction = typeof factions.$inferSelect;
export type Place = typeof places.$inferSelect;
export type Character = typeof characters.$inferSelect;
export type CharacterRelationship = typeof characterRelationships.$inferSelect;
export type CharacterPsychology = typeof characterPsychology.$inferSelect;
export type Season = typeof seasons.$inferSelect;
export type Episode = typeof episodes.$inferSelect;
export type NarrativeChunk = typeof narrativeChunks.$inferSelect;
export type ChunkMetadata = typeof chunkMetadata.$inferSelect;

// Insert schemas (only for the existing user table, as we're not creating new data)
export const insertUserSchema = createInsertSchema(users).pick({
  username: true,
  password: true,
});

export type InsertUser = z.infer<typeof insertUserSchema>;