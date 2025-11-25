import pg from 'pg';
import { drizzle } from 'drizzle-orm/node-postgres';
import * as schema from "@shared/schema";

const { Pool } = pg;

export const pool = process.env.DATABASE_URL
  ? new Pool({ connectionString: process.env.DATABASE_URL })
  : null;

export const db = pool
  ? drizzle(pool, { schema })
  : null;

// Cache pools to avoid creating too many connections
const pools: Record<string, pg.Pool> = {};

export function getDb(slot?: number | null) {
  if (!process.env.DATABASE_URL) return null;

  let connectionString = process.env.DATABASE_URL;

  if (slot) {
    const dbName = `save_${String(slot).padStart(2, '0')}`;
    try {
      const url = new URL(connectionString);
      url.pathname = `/${dbName}`;
      connectionString = url.toString();
    } catch (e) {
      console.error("Invalid DATABASE_URL", e);
      return null;
    }
  }

  if (!pools[connectionString]) {
    pools[connectionString] = new Pool({ connectionString });
  }

  return drizzle(pools[connectionString], { schema });
}
