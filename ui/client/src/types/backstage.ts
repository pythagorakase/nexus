export type BackstageKind = "character" | "relation" | "place" | "faction";

export interface BackstageTurnResponse {
  header: {
    slot: number;
    chunk_id: number;
    chunk_label: string;
    turn_label: string;
    world_time: string | null;
    skald_status: "writing" | "idle";
  };
  correspondence: {
    digest: string | null;
    compacted_through_chunk_id: number | null;
    digest_fresh: boolean;
    exchanges: Array<{
      chunk_id: number;
      turn_label: string;
      letters: Array<{
        seat: "writer" | "gaia" | "single_pass";
        body: string;
      }>;
    }>;
    held_threads: Array<{
      template_id: string;
      actor_name: string | null;
      streak_length: number;
      start_tick: number;
      start_turn_label: string;
    }>;
  };
  state_writes: {
    rows: Array<{
      kind: BackstageKind;
      label: string;
      field: string;
      old_value: unknown;
      new_value: unknown;
      operation: "set" | "bestow" | "clear";
      mechanism: string | null;
      held: boolean;
    }>;
    history: BackstageHistoryLine[];
  };
  orrery: {
    rows: Array<{
      template_id: string;
      actor_name: string | null;
      target_name: string | null;
      magnitude: number | null;
      brief: string | null;
      branch_label: string | null;
      event_type: string | null;
      drive_band: string | null;
    }>;
    counts: BackstageCounts;
    history: BackstageHistoryLine[];
  };
}

export interface BackstageCounts {
  fired: number;
  pressures: number;
  events: number;
}

export interface BackstageHistoryLine {
  chunk_id: number;
  turn_label: string;
  writes: number | null;
  fired: number | null;
  pressures: number | null;
  events: number | null;
}
