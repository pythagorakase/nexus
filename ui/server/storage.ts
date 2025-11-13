import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";

import {
  type Season,
  type Episode,
  type NarrativeChunk,
  type ChunkMetadata,
  type Character,
  type CharacterRelationship,
  type CharacterPsychology,
  type CharacterImage,
  type PlaceImage,
  type Place,
  type Zone,
  type Faction,
  seasons,
  episodes,
  narrativeChunks,
  chunkMetadata,
  characters,
  characterRelationships,
  characterPsychology,
  characterImages,
  placeImages,
  places,
  zones,
  factions
} from "@shared/schema";
import { db } from "./db";
import { eq, and, gte, lte, sql } from "drizzle-orm";

export interface IStorage {
  // Season methods
  getAllSeasons(): Promise<Season[]>;
  
  // Episode methods
  getEpisodesBySeason(seasonId: number): Promise<Episode[]>;
  
  // Narrative chunk methods
  getChunksBySeasonAndEpisode(seasonId: number, episodeId: number, offset?: number, limit?: number): Promise<{
    chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>;
    total: number;
  }>;
  getLatestChunk(): Promise<(NarrativeChunk & { metadata?: ChunkMetadata }) | null>;
  getAdjacentChunks(chunkId: number): Promise<{
    previous: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
    next: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
  }>;

  // Character methods
  getCharacters(startId?: number, endId?: number): Promise<Character[]>;
  getCharacterById(id: number): Promise<Character | undefined>;
  
  // Character relationship methods
  getCharacterRelationships(characterId: number): Promise<CharacterRelationship[]>;
  
  // Character psychology methods
  getCharacterPsychology(characterId: number): Promise<CharacterPsychology | undefined>;

  // Character image methods
  getCharacterImages(characterId: number): Promise<CharacterImage[]>;
  addCharacterImage(characterId: number, filePath: string, isMain: number, displayOrder: number): Promise<CharacterImage>;
  setMainCharacterImage(characterId: number, imageId: number): Promise<void>;
  deleteCharacterImage(imageId: number): Promise<void>;

  // Place methods
  getAllPlaces(): Promise<Place[]>;

  // Place image methods
  getPlaceImages(placeId: number): Promise<PlaceImage[]>;
  addPlaceImage(placeId: number, filePath: string, isMain: number, displayOrder: number): Promise<PlaceImage>;
  setMainPlaceImage(placeId: number, imageId: number): Promise<void>;
  deletePlaceImage(imageId: number): Promise<void>;
  
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
  async getChunksBySeasonAndEpisode(
    seasonId: number,
    episodeId: number,
    offset: number = 0,
    limit: number = 50
  ): Promise<{
    chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>;
    total: number;
  }> {
    // Get chunks with their metadata for a specific season and episode
    const chunksWithMetadata = await this.db
      .select({
        chunk: narrativeChunks,
        metadata: chunkMetadata
      })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(and(
        eq(chunkMetadata.season, seasonId),
        eq(chunkMetadata.episode, episodeId)
      ))
      .orderBy(narrativeChunks.id)
      .limit(limit)
      .offset(offset);

    // Get total count
    const countResult = await this.db
      .select({ count: sql<number>`count(*)` })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(and(
        eq(chunkMetadata.season, seasonId),
        eq(chunkMetadata.episode, episodeId)
      ));

    const total = Number(countResult[0]?.count || 0);

    // Map to the expected format
    const chunks = chunksWithMetadata.map(row => ({
      ...row.chunk,
      metadata: row.metadata || undefined
    }));

    return { chunks, total };
  }

  async getLatestChunk(): Promise<(NarrativeChunk & { metadata?: ChunkMetadata }) | null> {
    // Get the chunk with highest ID that has metadata
    const result = await this.db
      .select({
        chunk: narrativeChunks,
        metadata: chunkMetadata
      })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(sql`${chunkMetadata.id} IS NOT NULL`)
      .orderBy(sql`${narrativeChunks.id} DESC`)
      .limit(1);

    if (result.length === 0) {
      return null;
    }

    return {
      ...result[0].chunk,
      metadata: result[0].metadata || undefined
    };
  }

  async getAdjacentChunks(chunkId: number): Promise<{
    previous: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
    next: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
  }> {
    // Get previous chunk (highest ID less than current)
    const previousResult = await this.db
      .select({
        chunk: narrativeChunks,
        metadata: chunkMetadata
      })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(and(
        sql`${narrativeChunks.id} < ${chunkId}`,
        sql`${chunkMetadata.id} IS NOT NULL`
      ))
      .orderBy(sql`${narrativeChunks.id} DESC`)
      .limit(1);

    // Get next chunk (lowest ID greater than current)
    const nextResult = await this.db
      .select({
        chunk: narrativeChunks,
        metadata: chunkMetadata
      })
      .from(narrativeChunks)
      .leftJoin(chunkMetadata, eq(narrativeChunks.id, chunkMetadata.chunkId))
      .where(and(
        sql`${narrativeChunks.id} > ${chunkId}`,
        sql`${chunkMetadata.id} IS NOT NULL`
      ))
      .orderBy(sql`${narrativeChunks.id} ASC`)
      .limit(1);

    return {
      previous: previousResult.length > 0
        ? { ...previousResult[0].chunk, metadata: previousResult[0].metadata || undefined }
        : null,
      next: nextResult.length > 0
        ? { ...nextResult[0].chunk, metadata: nextResult[0].metadata || undefined }
        : null,
    };
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

  // Character image methods
  async getCharacterImages(characterId: number): Promise<CharacterImage[]> {
    return await this.db.select()
      .from(characterImages)
      .where(eq(characterImages.characterId, characterId))
      .orderBy(characterImages.displayOrder);
  }

  async addCharacterImage(characterId: number, filePath: string, isMain: number, displayOrder: number): Promise<CharacterImage> {
    const result = await this.db.insert(characterImages)
      .values({ characterId, filePath, isMain, displayOrder })
      .returning();
    return result[0];
  }

  async setMainCharacterImage(characterId: number, imageId: number): Promise<void> {
    // First, unset all images for this character
    await this.db.update(characterImages)
      .set({ isMain: 0 })
      .where(eq(characterImages.characterId, characterId));

    // Then set the specified image as main
    await this.db.update(characterImages)
      .set({ isMain: 1 })
      .where(eq(characterImages.id, imageId));
  }

  async deleteCharacterImage(imageId: number): Promise<void> {
    await this.db.delete(characterImages)
      .where(eq(characterImages.id, imageId));
  }

  // Place methods
  async getAllPlaces(): Promise<Place[]> {
    // Use raw SQL to extract coordinates as GeoJSON from PostGIS geography
    const result = await this.db.execute(sql`
      SELECT
        id,
        name,
        type::text,
        zone,
        summary,
        inhabitants,
        history,
        current_status,
        secrets,
        extra_data,
        created_at,
        updated_at,
        ST_AsGeoJSON(coordinates)::json as geometry
      FROM places
      ORDER BY id
    `);

    return (result.rows as any[]).map(row => ({
      id: Number(row.id),
      name: row.name as string,
      type: row.type ?? null,
      zone: row.zone ? Number(row.zone) : null,
      summary: row.summary ?? null,
      inhabitants: row.inhabitants ?? null,
      history: row.history ?? null,
      currentStatus: row.current_status ?? null,
      secrets: row.secrets ?? null,
      extraData: row.extra_data ?? null,
      createdAt: row.created_at ? new Date(row.created_at) : null,
      updatedAt: row.updated_at ? new Date(row.updated_at) : null,
      geometry: row.geometry ?? null,
    })) as Place[];
  }

  // Place image methods
  async getPlaceImages(placeId: number): Promise<PlaceImage[]> {
    return await this.db.select()
      .from(placeImages)
      .where(eq(placeImages.placeId, placeId))
      .orderBy(placeImages.displayOrder);
  }

  async addPlaceImage(placeId: number, filePath: string, isMain: number, displayOrder: number): Promise<PlaceImage> {
    const result = await this.db.insert(placeImages)
      .values({ placeId, filePath, isMain, displayOrder })
      .returning();
    return result[0];
  }

  async setMainPlaceImage(placeId: number, imageId: number): Promise<void> {
    // First, unset all images for this place
    await this.db.update(placeImages)
      .set({ isMain: 0 })
      .where(eq(placeImages.placeId, placeId));

    // Then set the specified image as main
    await this.db.update(placeImages)
      .set({ isMain: 1 })
      .where(eq(placeImages.id, imageId));
  }

  async deletePlaceImage(imageId: number): Promise<void> {
    await this.db.delete(placeImages)
      .where(eq(placeImages.id, imageId));
  }

  // Zone methods
  async getAllZones(): Promise<Zone[]> {
    // Use raw SQL to extract boundary as text from PostGIS geometry
    const result = await this.db.execute(sql`
      SELECT
        id,
        name,
        summary,
        boundary::text
      FROM zones
      ORDER BY id
    `);

    return (result.rows as any[]).map(row => ({
      id: Number(row.id),
      name: row.name,
      summary: row.summary,
      boundary: row.boundary ?? null,
    })) as Zone[];
  }

  // Faction methods
  async getAllFactions(): Promise<Faction[]> {
    return await this.db.select().from(factions).orderBy(factions.id);
  }
}

const toNumber = (value: unknown): number | null => {
  const parsed = typeof value === "string" ? Number.parseFloat(value) : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const coerceJson = <T>(value: unknown): T | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === "object") return value as T;
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
};

class MemStorage implements IStorage {
  private seasons: Season[] = [];
  private episodes: Episode[] = [];
  private chunks: NarrativeChunk[] = [];
  private metadata: ChunkMetadata[] = [];
  private characters: Character[] = [];
  private characterRelationships: CharacterRelationship[] = [];
  private characterPsychology: CharacterPsychology[] = [];
  private characterImages: CharacterImage[] = [];
  private placeImages: PlaceImage[] = [];
  private places: Place[] = [];
  private zones: Zone[] = [];
  private factions: Faction[] = [];
  private nextCharacterImageId = 1;
  private nextPlaceImageId = 1;

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
      id: Number(season.id),
      summary: coerceJson<Record<string, unknown>>(season.summary) ?? season.summary ?? null,
    })) as Season[];

    this.episodes = load<any[]>("episodes_", []).map((episode) => ({
      season: Number(episode.season),
      episode: Number(episode.episode),
      chunkSpan: episode.chunk_span ?? null,
      summary: coerceJson<Record<string, unknown>>(episode.summary) ?? episode.summary ?? null,
      tempSpan: episode.temp_span ?? null,
    })) as Episode[];

    this.chunks = load<any[]>("narrative_chunks_", []).map((chunk) => ({
      id: Number(chunk.id),
      rawText: chunk.raw_text,
      createdAt: chunk.created_at ?? null,
    })) as NarrativeChunk[];

    this.metadata = load<any[]>("chunk_metadata_", []).map((meta) => ({
      id: Number(meta.id),
      chunkId: Number(meta.chunk_id),
      season: meta.season !== undefined ? Number(meta.season) : null,
      episode: meta.episode !== undefined ? Number(meta.episode) : null,
      scene: meta.scene !== undefined ? Number(meta.scene) : null,
      worldLayer: meta.world_layer ?? null,
      timeDelta: meta.time_delta ?? null,
      place: meta.place !== undefined ? Number(meta.place) : null,
      metadataVersion: meta.metadata_version ?? null,
      generationDate: meta.generation_date ?? null,
      slug: meta.slug ?? null,
    })) as ChunkMetadata[];

    this.characters = load<any[]>("characters_", []).map((character) => ({
      id: Number(character.id),
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
      character1Id: toNumber(rel.character1Id ?? rel.character1_id) ?? 0,
      character2Id: toNumber(rel.character2Id ?? rel.character2_id) ?? 0,
      relationshipType: rel.relationshipType ?? rel.relationship_type,
      emotionalValence: rel.emotionalValence ?? rel.emotional_valence,
      dynamic: rel.dynamic,
      recentEvents: rel.recentEvents ?? rel.recent_events,
      history: rel.history,
      extraData: coerceJson<Record<string, unknown>>(rel.extraData ?? rel.extra_data) ?? null,
      createdAt: rel.createdAt ?? rel.created_at ?? null,
      updatedAt: rel.updatedAt ?? rel.updated_at ?? null,
    })) as CharacterRelationship[];

    const rawPsychology = load<any[]>("character_psychology_", []);
    this.characterPsychology = rawPsychology.map((entry) => ({
      characterId: Number(entry.characterId ?? entry.character_id),
      selfConcept: coerceJson<Record<string, unknown>>(entry.selfConcept ?? entry.self_concept) ?? null,
      behavior: coerceJson<Record<string, unknown>>(entry.behavior) ?? entry.behavior ?? null,
      cognitiveFramework:
        coerceJson<Record<string, unknown>>(entry.cognitiveFramework ?? entry.cognitive_framework) ?? null,
      temperament: coerceJson<Record<string, unknown>>(entry.temperament) ?? entry.temperament ?? null,
      relationalStyle:
        coerceJson<Record<string, unknown>>(entry.relationalStyle ?? entry.relational_style) ?? null,
      defenseMechanisms:
        coerceJson<Record<string, unknown>>(entry.defenseMechanisms ?? entry.defense_mechanisms) ?? null,
      characterArc: coerceJson<Record<string, unknown>>(entry.characterArc ?? entry.character_arc) ?? null,
      secrets: coerceJson<Record<string, unknown>>(entry.secrets) ?? entry.secrets ?? null,
      validationEvidence:
        coerceJson<Record<string, unknown>>(entry.validationEvidence ?? entry.validation_evidence) ?? null,
      createdAt: entry.createdAt ?? entry.created_at ?? null,
      updatedAt: entry.updatedAt ?? entry.updated_at ?? null,
    })) as CharacterPsychology[];
    this.places = load<any[]>("places_", []).map((place) => ({
      id: Number(place.id),
      name: place.name,
      type: place.type ?? null,
      zone: toNumber(place.zone_id ?? place.zone) ?? null,
      summary: place.summary ?? null,
      inhabitants: Array.isArray(place.inhabitants)
        ? place.inhabitants
        : place.inhabitants ?? null,
      history: place.history ?? null,
      currentStatus: place.current_status ?? null,
      secrets: place.secrets ?? null,
      extraData: coerceJson<Record<string, unknown>>(place.extra_data) ?? place.extra_data ?? null,
      createdAt: place.created_at ? new Date(place.created_at) : null,
      updatedAt: place.updated_at ? new Date(place.updated_at) : null,
      coordinates: place.coordinates ?? place.geom ?? null,
      geom: place.geom ?? null,
    })) as Place[];

    this.zones = load<any[]>("zones_", []).map((zone) => ({
      id: Number(zone.id),
      name: zone.name,
      summary: zone.summary ?? null,
      boundary: zone.boundary ?? null,
    })) as Zone[];

    this.factions = load<any[]>("factions_", []).map((faction) => ({
      id: Number(faction.id),
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

  async getAllSeasons(): Promise<Season[]> {
    return this.seasons;
  }

  async getEpisodesBySeason(seasonId: number): Promise<Episode[]> {
    return this.episodes
      .filter((episode) => episode.season === seasonId)
      .sort((a, b) => a.episode - b.episode);
  }

  async getChunksBySeasonAndEpisode(
    seasonId: number,
    episodeId: number,
    offset: number = 0,
    limit: number = 50,
  ): Promise<{ chunks: Array<NarrativeChunk & { metadata?: ChunkMetadata }>; total: number }> {
    const metadataForEpisode = this.metadata.filter(
      (meta) => meta.season === seasonId && meta.episode === episodeId
    );
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

  async getLatestChunk(): Promise<(NarrativeChunk & { metadata?: ChunkMetadata }) | null> {
    // Get chunk with highest ID that has metadata
    const chunksWithMetadata = this.chunks
      .map((chunk) => ({
        ...chunk,
        metadata: this.metadata.find((meta) => meta.chunkId === chunk.id),
      }))
      .filter((chunk) => chunk.metadata !== undefined)
      .sort((a, b) => b.id - a.id);

    return chunksWithMetadata[0] || null;
  }

  async getAdjacentChunks(chunkId: number): Promise<{
    previous: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
    next: (NarrativeChunk & { metadata?: ChunkMetadata }) | null;
  }> {
    const chunksWithMetadata = this.chunks
      .map((chunk) => ({
        ...chunk,
        metadata: this.metadata.find((meta) => meta.chunkId === chunk.id),
      }))
      .filter((chunk) => chunk.metadata !== undefined)
      .sort((a, b) => a.id - b.id);

    // Find previous chunk (highest ID less than current)
    const previous = chunksWithMetadata
      .filter((chunk) => chunk.id < chunkId)
      .sort((a, b) => b.id - a.id)[0] || null;

    // Find next chunk (lowest ID greater than current)
    const next = chunksWithMetadata
      .filter((chunk) => chunk.id > chunkId)
      .sort((a, b) => a.id - b.id)[0] || null;

    return { previous, next };
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

  async getCharacterImages(characterId: number): Promise<CharacterImage[]> {
    return this.characterImages
      .filter((img) => img.characterId === characterId)
      .sort((a, b) => a.displayOrder - b.displayOrder);
  }

  async addCharacterImage(characterId: number, filePath: string, isMain: number, displayOrder: number): Promise<CharacterImage> {
    const image: CharacterImage = {
      id: this.nextCharacterImageId++,
      characterId,
      filePath,
      isMain,
      displayOrder,
      uploadedAt: new Date(),
    };
    this.characterImages.push(image);
    return image;
  }

  async setMainCharacterImage(characterId: number, imageId: number): Promise<void> {
    this.characterImages.forEach((img) => {
      if (img.characterId === characterId) {
        img.isMain = img.id === imageId ? 1 : 0;
      }
    });
  }

  async deleteCharacterImage(imageId: number): Promise<void> {
    this.characterImages = this.characterImages.filter((img) => img.id !== imageId);
  }

  async getAllPlaces(): Promise<Place[]> {
    return this.places;
  }

  async getPlaceImages(placeId: number): Promise<PlaceImage[]> {
    return this.placeImages
      .filter((img) => img.placeId === placeId)
      .sort((a, b) => a.displayOrder - b.displayOrder);
  }

  async addPlaceImage(placeId: number, filePath: string, isMain: number, displayOrder: number): Promise<PlaceImage> {
    const image: PlaceImage = {
      id: this.nextPlaceImageId++,
      placeId,
      filePath,
      isMain,
      displayOrder,
      uploadedAt: new Date(),
    };
    this.placeImages.push(image);
    return image;
  }

  async setMainPlaceImage(placeId: number, imageId: number): Promise<void> {
    this.placeImages.forEach((img) => {
      if (img.placeId === placeId) {
        img.isMain = img.id === imageId ? 1 : 0;
      }
    });
  }

  async deletePlaceImage(imageId: number): Promise<void> {
    this.placeImages = this.placeImages.filter((img) => img.id !== imageId);
  }

  async getAllZones(): Promise<Zone[]> {
    return this.zones;
  }

  async getAllFactions(): Promise<Faction[]> {
    return this.factions;
  }
}

export const storage: IStorage = db ? new PostgresStorage() : new MemStorage();
