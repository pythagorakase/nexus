/**
 * Shapes for the /api/local-models surface (FastAPI local-inference
 * manager). Single source of truth for the client — extend here, not
 * locally. Field semantics worth pinning:
 *
 * - Catalog↔installed join: there is no server-side join; an entry is
 *   installed iff `models_dir + "/" + subdir + "/" + filename` equals an
 *   installed row's `path` exactly (split sets are collapsed to their
 *   first shard on both sides).
 * - `system_ram_gb` is total physical memory in GiB — the unit
 *   `min_ram_gb` is quoted in, so the two compare directly.
 * - Download `state` "done"/"failed" persist until the next POST
 *   /download overwrites the record; completion is `state === "done"`,
 *   never `progress === 1` (total_bytes is a decimal-GB estimate).
 */

export interface LocalCatalogEntry {
  family: string;
  label: string;
  hf_repo: string;
  subdir: string;
  filename: string;
  quant: string;
  size_gb: number;
  min_ram_gb: number;
}

export interface LocalInstalledModel {
  path: string;
  filename: string;
  arch: string | null;
  quant: string | null;
  size_bytes: number;
  verified: boolean;
  active: boolean;
}

export interface LocalActiveModel {
  gguf_path: string;
  ready: boolean;
  failed: boolean;
  error?: string;
}

export interface LocalModelsStatus {
  models_dir: string;
  system_ram_gb: number;
  catalog: LocalCatalogEntry[];
  installed: LocalInstalledModel[];
  active: LocalActiveModel | null;
}

export interface LocalDownloadIdle {
  state: "idle";
}

export interface LocalDownloadRecord {
  state: "downloading" | "done" | "failed";
  family: string;
  quant: string;
  downloaded_bytes: number;
  total_bytes: number;
  progress: number;
  files: string[];
  local_dir: string;
  error?: string;
}

export type LocalDownloadStatus = LocalDownloadIdle | LocalDownloadRecord;
