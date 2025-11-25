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

const slotPools = new Map<number, pg.Pool>();
const slotDbs = new Map<number, ReturnType<typeof drizzle>>();

export function getDb(slot?: number | null) {
  if (slot === undefined || slot === null) {
    return db;
  }

  const slotUrl = process.env[`DATABASE_URL_SLOT_${slot}`];

  if (!slotUrl) {
    return db;
  }

  if (!slotPools.has(slot)) {
    const slotPool = new Pool({ connectionString: slotUrl });
    slotPools.set(slot, slotPool);
    slotDbs.set(slot, drizzle(slotPool, { schema }));
  }

  return slotDbs.get(slot) ?? db;
}
