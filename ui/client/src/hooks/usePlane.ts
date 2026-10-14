/**
 * The plane of the gateway that serves this client (#824, Decision 824-Q7).
 *
 * `GET /health` names the projection that answered it. The connectivity probe
 * in useNarrativeEngine writes each successful answer into this query's
 * cache. The plane only shapes the interface; the projections enforce it.
 */
import { useQuery } from "@tanstack/react-query";

export type Plane = "player" | "operator";

export interface HealthPayload {
  status: string;
  service: string;
  plane: Plane;
}

export const HEALTH_QUERY_KEY = ["/health"] as const;

/** The serving plane, or undefined until `/health` answers. */
export function usePlane(): Plane | undefined {
  return useQuery<HealthPayload>({ queryKey: [...HEALTH_QUERY_KEY] }).data?.plane;
}
