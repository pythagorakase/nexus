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
  // User methods
  async getUser(id: string): Promise<User | undefined> {
    const result = await db.select().from(users).where(eq(users.id, id)).limit(1);
    return result[0];
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    const result = await db.select().from(users).where(eq(users.username, username)).limit(1);
    return result[0];
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const result = await db.insert(users).values(insertUser).returning();
    return result[0];
  }

  // Season methods
  async getAllSeasons(): Promise<Season[]> {
    return await db.select().from(seasons).orderBy(seasons.id);
  }

  // Episode methods
  async getEpisodesBySeason(seasonId: number): Promise<Episode[]> {
    return await db.select()
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
    const chunksWithMetadata = await db
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
    const countResult = await db
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
      return await db.select()
        .from(characters)
        .where(and(
          gte(characters.id, startId),
          lte(characters.id, endId)
        ))
        .orderBy(characters.id);
    } else if (startId !== undefined) {
      return await db.select()
        .from(characters)
        .where(gte(characters.id, startId))
        .orderBy(characters.id);
    } else if (endId !== undefined) {
      return await db.select()
        .from(characters)
        .where(lte(characters.id, endId))
        .orderBy(characters.id);
    }
    
    return await db.select()
      .from(characters)
      .orderBy(characters.id);
  }

  async getCharacterById(id: number): Promise<Character | undefined> {
    const result = await db.select().from(characters).where(eq(characters.id, id)).limit(1);
    return result[0];
  }

  // Character relationship methods
  async getCharacterRelationships(characterId: number): Promise<CharacterRelationship[]> {
    return await db.select()
      .from(characterRelationships)
      .where(
        sql`${characterRelationships.character1Id} = ${characterId} OR ${characterRelationships.character2Id} = ${characterId}`
      );
  }

  // Character psychology methods
  async getCharacterPsychology(characterId: number): Promise<CharacterPsychology | undefined> {
    const result = await db.select()
      .from(characterPsychology)
      .where(eq(characterPsychology.characterId, characterId))
      .limit(1);
    return result[0];
  }

  // Place methods
  async getAllPlaces(): Promise<Place[]> {
    return await db.select().from(places).orderBy(places.id);
  }

  // Zone methods
  async getAllZones(): Promise<Zone[]> {
    return await db.select().from(zones).orderBy(zones.id);
  }

  // Faction methods
  async getAllFactions(): Promise<Faction[]> {
    return await db.select().from(factions).orderBy(factions.id);
  }
}

// Export PostgresStorage instead of MemStorage
export const storage = new PostgresStorage();