// Typed fetchers for the dev-only Orrery audit endpoints. The gateway
// registers /api/dev/orrery/* only when [orrery.dashboard] enabled is true
// in nexus.toml; a 404 here means the server-side flag is off, which the
// page surfaces as an explicit setup notice (see index.tsx).

import type {
  CatalogPayload,
  ContextPayload,
  CoveragePayload,
  OverridesRequest,
  ResolvePayload,
  VocabPayload,
} from "./types";

const BASE = "/api/dev/orrery";

export class OrreryApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* non-JSON error body: keep statusText */
    }
    throw new OrreryApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export function fetchResolve(params: {
  slot: number;
  anchorChunkId?: number | null;
  overrides?: Partial<OverridesRequest> | null;
}): Promise<ResolvePayload> {
  return request<ResolvePayload>("/resolve", {
    method: "POST",
    body: JSON.stringify({
      slot: params.slot,
      anchor_chunk_id: params.anchorChunkId ?? null,
      overrides: params.overrides ?? null,
    }),
  });
}

export function fetchCatalog(): Promise<CatalogPayload> {
  return request<CatalogPayload>("/catalog");
}

export function fetchEntityContext(params: {
  slot: number;
  entityIds: number[];
  anchorChunkId?: number | null;
}): Promise<ContextPayload> {
  return request<ContextPayload>("/context/entities", {
    method: "POST",
    body: JSON.stringify({
      slot: params.slot,
      entity_ids: params.entityIds,
      anchor_chunk_id: params.anchorChunkId ?? null,
      recent_events_limit: 3,
    }),
  });
}

export function fetchCoverage(params: {
  slot: number;
  count?: number;
  stride?: number;
  endChunkId?: number | null;
}): Promise<CoveragePayload> {
  return request<CoveragePayload>("/coverage", {
    method: "POST",
    body: JSON.stringify({
      slot: params.slot,
      count: params.count ?? 10,
      stride: params.stride ?? 1,
      end_chunk_id: params.endChunkId ?? null,
    }),
  });
}

export function fetchVocab(slot: number): Promise<VocabPayload> {
  return request<VocabPayload>(`/vocab?slot=${slot}`);
}
