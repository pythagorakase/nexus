import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";

import {
  type User,
  type InsertUser,
  type Season,
  type Episode,
  type NarrativeChunk,
  type ChunkMetadata,
  type Character,
  type CharacterRelationship,
  type CharacterPsychology,
  type Place,
  type Zone,
  type Faction,
  users,
  seasons,
  episodes,
  narrativeChunks,
  chunkMetadata,
  characters,
  characterRelationships,
  characterPsychology,
  places,
  zones,
  factions
} from "@shared/schema";
import { db } from "./db";
import { eq, and, gte, lte, sql } from "drizzle-orm";

export interface IStorage {
  // User methods
  getUser(id: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;

  // Season methods
  getAllSeasons(): Promise<Season[]>;
  
  // Episode methods
  getEpisodesBySeason(seasonId: number): Promise<Episode[]>;
  
  // Narrative chunk methods
  getChunksByEpisode(episodeId: number, offset?: number, limit?: number): Promise<{
    chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>;
    total: number;
  }>;
  
  // Character methods
  getCharacters(startId?: number, endId?: number): Promise<Character[]>;
  getCharacterById(id: number): Promise<Character | undefined>;
  
  // Character relationship methods
  getCharacterRelationships(characterId: number): Promise<CharacterRelationship[]>;
  
  // Character psychology methods
  getCharacterPsychology(characterId: number): Promise<CharacterPsychology | undefined>;
  
  // Place methods
  getAllPlaces(): Promise<Place[]>;
  
  // Zone methods
  getAllZones(): Promise<Zone[]>;
  
  // Faction methods
  getAllFactions(): Promise<Faction[]>;
}

export class PostgresStorage implements IStorage {
  private db;

  constructor() {
    if (!db) {
      throw new Error("PostgresStorage requires a configured database; missing DATABASE_URL");
    }
    this.db = db;
  }
  // User methods
  async getUser(id: string): Promise<User | undefined> {
    const result = await this.db.select().from(users).where(eq(users.id, id)).limit(1);
    return result[0];
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    const result = await this.db.select().from(users).where(eq(users.username, username)).limit(1);
    return result[0];
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const result = await this.db.insert(users).values(insertUser).returning();
    return result[0];
  }

  // Season methods
  async getAllSeasons(): Promise<Season[]> {
    return await this.db.select().from(seasons).orderBy(seasons.id);
  }

  // Episode methods
  async getEpisodesBySeason(seasonId: number): Promise<Episode[]> {
    return await this.db.select()
      .from(episodes)
      .where(eq(episodes.season, seasonId))
      .orderBy(episodes.episode);
  }

  // Narrative chunk methods
  async getChunksByEpisode(
    episodeId: number, 
    offset: number = 0, 
    limit: number = 50
  ): Promise<{
    chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>;
    total: number;
  }> {
    // Get chunks with their metadata for a specific episode
    const chunksWithMetadata = await this.db
      .select({
        chunk: narrativeChunks,
        metadata: chunkMetadata
      })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(eq(chunkMetadata.episode, episodeId))
      .orderBy(narrativeChunks.id)
      .limit(limit)
      .offset(offset);

    // Get total count
    const countResult = await this.db
      .select({ count: sql<number>`count(*)` })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(eq(chunkMetadata.episode, episodeId));

    const total = Number(countResult[0]?.count || 0);

    // Map to the expected format
    const chunks = chunksWithMetadata.map(row => ({
      ...row.chunk,
      metadata: row.metadata || undefined
    }));

    return { chunks, total };
  }

  // Character methods
  async getCharacters(startId?: number, endId?: number): Promise<Character[]> {
    if (startId !== undefined && endId !== undefined) {
      return await this.db.select()
        .from(characters)
        .where(and(
          gte(characters.id, startId),
          lte(characters.id, endId)
        ))
        .orderBy(characters.id);
    } else if (startId !== undefined) {
      return await this.db.select()
        .from(characters)
        .where(gte(characters.id, startId))
        .orderBy(characters.id);
    } else if (endId !== undefined) {
      return await this.db.select()
        .from(characters)
        .where(lte(characters.id, endId))
        .orderBy(characters.id);
    }
    
    return await this.db.select()
      .from(characters)
      .orderBy(characters.id);
  }

  async getCharacterById(id: number): Promise<Character | undefined> {
    const result = await this.db.select().from(characters).where(eq(characters.id, id)).limit(1);
    return result[0];
  }

  // Character relationship methods
  async getCharacterRelationships(characterId: number): Promise<CharacterRelationship[]> {
    return await this.db.select()
      .from(characterRelationships)
      .where(
        sql`${characterRelationships.character1Id} = ${characterId} OR ${characterRelationships.character2Id} = ${characterId}`
      );
  }

  // Character psychology methods
  async getCharacterPsychology(characterId: number): Promise<CharacterPsychology | undefined> {
    const result = await this.db.select()
      .from(characterPsychology)
      .where(eq(characterPsychology.characterId, characterId))
      .limit(1);
    return result[0];
  }

  // Place methods
  async getAllPlaces(): Promise<Place[]> {
    // Use raw SQL to extract coordinates properly from PostGIS geography
    const result = await this.db.execute(sql`
      SELECT
        id,
        name,
        type,
        zone,
        summary,
        inhabitants,
        history,
        current_status,
        secrets,
        extra_data,
        created_at,
        updated_at,
        ST_X(coordinates::geometry) as longitude,
        ST_Y(coordinates::geometry) as latitude
      FROM places
      ORDER BY id
    `);

    return (result.rows as any[]).map(row => ({
      id: row.id,
      name: row.name,
      type: row.type,
      zoneId: row.zone,
      summary: row.summary,
      inhabitants: row.inhabitants,
      history: row.history,
      currentStatus: row.current_status,
      secrets: row.secrets,
      extraData: row.extra_data,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      longitude: row.longitude,
      latitude: row.latitude,
    })) as Place[];
  }

  // Zone methods
  async getAllZones(): Promise<Zone[]> {
    // Use raw SQL to extract boundary as GeoJSON from PostGIS geometry
    const result = await this.db.execute(sql`
      SELECT
        id,
        name,
        summary,
        ST_AsGeoJSON(boundary)::text as boundary_geojson
      FROM zones
      ORDER BY id
    `);

    return (result.rows as any[]).map(row => ({
      id: row.id,
      name: row.name,
      summary: row.summary,
      boundary: row.boundary_geojson ? JSON.parse(row.boundary_geojson) : null,
      worldlayerId: null,
      createdAt: null,
      updatedAt: null,
    })) as Zone[];
  }

  // Faction methods
  async getAllFactions(): Promise<Faction[]> {
    return await this.db.select().from(factions).orderBy(factions.id);
  }
}

class MemStorage implements IStorage {
  private seasons: Season[] = [];
  private episodes: Episode[] = [];
  private chunks: NarrativeChunk[] = [];
  private metadata: ChunkMetadata[] = [];
  private characters: Character[] = [];
  private characterRelationships: CharacterRelationship[] = [];
  private characterPsychology: CharacterPsychology[] = [];
  private places: Place[] = [];
  private zones: Zone[] = [];
  private factions: Faction[] = [];
  private users = new Map<string, User>();

  constructor() {
    const __dirname = path.dirname(fileURLToPath(import.meta.url));
    const assetsDir = path.join(__dirname, "..", "attached_assets");
    const files = fs.existsSync(assetsDir) ? fs.readdirSync(assetsDir) : [];

    const load = <T>(prefix: string, fallback: T): T => {
      const match = files.find((file) => file.startsWith(prefix) && file.endsWith(".json"));
      if (!match) {
        return fallback;
      }
      try {
        const raw = fs.readFileSync(path.join(assetsDir, match), "utf-8");
        return JSON.parse(raw) as T;
      } catch (error) {
        console.warn(`Failed to load ${prefix}:`, error);
        return fallback;
      }
    };

    this.seasons = load<any[]>("seasons_", []).map((season) => ({
      id: season.id,
      summary: season.summary ?? null,
    })) as Season[];

    this.episodes = load<any[]>("episodes_", []).map((episode) => ({
      season: episode.season,
      episode: episode.episode,
      chunkSpan: episode.chunk_span ?? null,
      summary: episode.summary ?? null,
      tempSpan: episode.temp_span ?? null,
    })) as Episode[];

    this.chunks = load<any[]>("narrative_chunks_", []).map((chunk) => ({
      id: chunk.id,
      rawText: chunk.raw_text,
      createdAt: chunk.created_at ?? null,
    })) as NarrativeChunk[];

    this.metadata = load<any[]>("chunk_metadata_", []).map((meta) => ({
      id: meta.id,
      chunkId: meta.chunk_id,
      season: meta.season ?? null,
      episode: meta.episode ?? null,
      scene: meta.scene ?? null,
      worldLayer: meta.world_layer ?? null,
      timeDelta: meta.time_delta ?? null,
      place: meta.place ?? null,
      atmosphere: meta.atmosphere ?? null,
      arcPosition: meta.arc_position ?? null,
      direction: meta.direction ?? null,
      magnitude: meta.magnitude ?? null,
      characterElements: meta.character_elements ?? null,
      perspective: meta.perspective ?? null,
      interactions: meta.interactions ?? null,
      dialogueAnalysis: meta.dialogue_analysis ?? null,
      emotionalTone: meta.emotional_tone ?? null,
      narrativeFunction: meta.narrative_function ?? null,
      narrativeTechniques: meta.narrative_techniques ?? null,
      thematicElements: meta.thematic_elements ?? null,
      causality: meta.causality ?? null,
      continuityMarkers: meta.continuity_markers ?? null,
      metadataVersion: meta.metadata_version ?? null,
      generationDate: meta.generation_date ?? null,
      slug: meta.slug ?? null,
    })) as ChunkMetadata[];

    this.characters = load<any[]>("characters_", []).map((character) => ({
      id: character.id,
      name: character.name,
      summary: character.summary ?? null,
      appearance: character.appearance ?? null,
      background: character.background ?? null,
      personality: character.personality ?? null,
      emotionalState: character.emotional_state ?? null,
      currentActivity: character.current_activity ?? null,
      currentLocation: character.current_location ?? null,
      extraData: character.extra_data ?? null,
      createdAt: character.created_at ?? null,
      updatedAt: character.updated_at ?? null,
    })) as Character[];
    const parsePoint = (value: unknown): { latitude: number; longitude: number } | null => {
      if (typeof value !== "string") return null;
      const match = value.match(/POINT(?:ZM)?\((-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/i);
      if (!match) return null;
      const longitude = Number(match[1]);
      const latitude = Number(match[2]);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return null;
      }
      return { latitude, longitude };
    };

    const rawRelationships = load<any[]>("character_relationships_", []);
    this.characterRelationships = rawRelationships.map((rel) => ({
      character1Id: rel.character1Id ?? rel.character1_id,
      character2Id: rel.character2Id ?? rel.character2_id,
      relationshipType: rel.relationshipType ?? rel.relationship_type,
      emotionalValence: rel.emotionalValence ?? rel.emotional_valence,
      dynamic: rel.dynamic,
      recentEvents: rel.recentEvents ?? rel.recent_events,
      history: rel.history,
      extraData: rel.extraData ?? rel.extra_data ?? null,
      createdAt: rel.createdAt ?? rel.created_at ?? null,
      updatedAt: rel.updatedAt ?? rel.updated_at ?? null,
    })) as CharacterRelationship[];

    const rawPsychology = load<any[]>("character_psychology_", []);
    this.characterPsychology = rawPsychology.map((entry) => ({
      characterId: entry.characterId ?? entry.character_id,
      selfConcept: entry.selfConcept ?? entry.self_concept ?? null,
      behavior: entry.behavior ?? null,
      cognitiveFramework: entry.cognitiveFramework ?? entry.cognitive_framework ?? null,
      temperament: entry.temperament ?? null,
      relationalStyle: entry.relationalStyle ?? entry.relational_style ?? null,
      defenseMechanisms: entry.defenseMechanisms ?? entry.defense_mechanisms ?? null,
      characterArc: entry.characterArc ?? entry.character_arc ?? null,
      secrets: entry.secrets ?? null,
      validationEvidence: entry.validationEvidence ?? entry.validation_evidence ?? null,
      createdAt: entry.createdAt ?? entry.created_at ?? null,
      updatedAt: entry.updatedAt ?? entry.updated_at ?? null,
    })) as CharacterPsychology[];
    this.places = load<any[]>("places_", []).map((place) => {
      const parsedCoords = parsePoint(place.coordinates ?? place.geom ?? null);
      return {
        id: place.id,
        name: place.name,
        type: place.type ?? null,
        description: place.description ?? null,
        summary: place.summary ?? null,
        latitude: place.latitude ?? parsedCoords?.latitude ?? null,
        longitude: place.longitude ?? parsedCoords?.longitude ?? null,
        elevation: place.elevation ?? null,
        address: place.address ?? null,
        district: place.district ?? null,
        zoneId: place.zone_id ?? place.zone ?? null,
        factionDominantId: place.faction_dominant_id ?? null,
        createdAt: place.created_at ?? null,
        updatedAt: place.updated_at ?? null,
      } as Place;
    }) as Place[];

    this.zones = load<any[]>("zones_", []).map((zone) => ({
      id: zone.id,
      name: zone.name,
      summary: zone.summary ?? null,
      boundary: zone.boundary ?? null,
      worldlayerId: zone.worldlayer_id ?? null,
      createdAt: zone.created_at ?? null,
      updatedAt: zone.updated_at ?? null,
    })) as Zone[];

    this.factions = load<any[]>("factions_", []).map((faction) => ({
      id: faction.id,
      name: faction.name,
      summary: faction.summary ?? null,
      ideology: faction.ideology ?? null,
      history: faction.history ?? null,
      currentActivity: faction.current_activity ?? null,
      hiddenAgenda: faction.hidden_agenda ?? null,
      territory: faction.territory ?? null,
      primaryLocation: faction.primary_location ?? null,
      powerLevel: faction.power_level ?? null,
      resources: faction.resources ?? null,
      extraData: faction.extra_data ?? null,
      createdAt: faction.created_at ?? null,
      updatedAt: faction.updated_at ?? null,
    })) as Faction[];
  }

  // User methods (minimal in-memory implementation)
  async getUser(id: string): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find((user) => user.username === username);
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const user: User = {
      id: randomUUID(),
      username: insertUser.username,
      password: insertUser.password,
    };
    this.users.set(user.id, user);
    return user;
  }

  async getAllSeasons(): Promise<Season[]> {
    return this.seasons;
  }

  async getEpisodesBySeason(seasonId: number): Promise<Episode[]> {
    return this.episodes
      .filter((episode) => episode.season === seasonId)
      .sort((a, b) => a.episode - b.episode);
  }

  async getChunksByEpisode(
    episodeId: number,
    offset: number = 0,
    limit: number = 50,
  ): Promise<{ chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>; total: number }> {
    const metadataForEpisode = this.metadata.filter((meta) => meta.episode === episodeId);
    const chunkIds = new Set(metadataForEpisode.map((meta) => meta.chunkId));
    const chunks = this.chunks.filter((chunk) => chunkIds.has(chunk.id));

    const sorted = chunks
      .map((chunk) => ({
        ...chunk,
        metadata: metadataForEpisode.find((meta) => meta.chunkId === chunk.id),
      }))
      .sort((a, b) => a.id - b.id);

    return {
      total: sorted.length,
      chunks: sorted.slice(offset, offset + limit),
    };
  }

  async getCharacters(startId?: number, endId?: number): Promise<Character[]> {
    return this.characters.filter((character) => {
      if (startId !== undefined && character.id < startId) {
        return false;
      }
      if (endId !== undefined && character.id > endId) {
        return false;
      }
      return true;
    });
  }

  async getCharacterById(id: number): Promise<Character | undefined> {
    return this.characters.find((character) => character.id === id);
  }

  async getCharacterRelationships(characterId: number): Promise<CharacterRelationship[]> {
    return this.characterRelationships.filter(
      (rel) => rel.character1Id === characterId || rel.character2Id === characterId,
    );
  }

  async getCharacterPsychology(characterId: number): Promise<CharacterPsychology | undefined> {
    return this.characterPsychology.find((entry) => entry.characterId === characterId);
  }

  async getAllPlaces(): Promise<Place[]> {
    return this.places;
  }

  async getAllZones(): Promise<Zone[]> {
    return this.zones;
  }

  async getAllFactions(): Promise<Faction[]> {
    return this.factions;
  }
}

export const storage: IStorage = db ? new PostgresStorage() : new MemStorage();
