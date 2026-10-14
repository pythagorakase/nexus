import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RETROGRADE_STAGES,
  getRetrogradeStatus,
  retrogradeStageOf,
  skippedRetrogradeStages,
} from "./narrative-api";

const ORCHESTRATOR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../nexus/agents/orrery/retrograde_orchestrator.py",
);

// Every gateway answer names the run owning the record and the poll interval.
const RECORD = { slot: 5, run_status: "running", error: null, run: "run-of-this-transition", status_poll_interval_seconds: 1 };

function serve(body: unknown, status = 200) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Retrograde status client", () => {
  it("mirrors the gateway's published stage vocabulary in pipeline order", () => {
    const source = readFileSync(ORCHESTRATOR, "utf-8");
    const tuple = source.match(/RETROGRADE_WIZARD_STAGES: tuple\[str, \.\.\.\] = \(([^)]*)\)/);
    expect(tuple, "RETROGRADE_WIZARD_STAGES in retrograde_orchestrator.py").not.toBeNull();
    const published = [...tuple![1].matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
    expect([...RETROGRADE_STAGES, "done"]).toEqual(published);
  });

  it("reads a slot's status and places the run at its stage", async () => {
    const fetch = serve({
      ...RECORD,
      stage: "expansion",
      detail: { candidates: 6, selected: 3 },
      updated_at: "2026-09-26T12:00:00+00:00",
      stages: [],
    });
    const status = await getRetrogradeStatus(5);
    expect(fetch).toHaveBeenCalledWith("/api/story/new/retrograde/status?slot=5");
    expect(retrogradeStageOf(status)).toBe("expansion");
  });

  it("places a failed run at the stage named in its detail", async () => {
    serve({ ...RECORD, run_status: "failed", error: "Failed", stage: "failed", detail: { stage: "embedding" }, stages: [] });
    expect(retrogradeStageOf(await getRetrogradeStatus(5))).toBe("embedding");
  });

  it("parses a derivation failure and places it at derivation", async () => {
    serve({
      ...RECORD,
      run_status: "failed",
      error: "Trait input derivation failed",
      stage: "failed",
      detail: { stage: "derivation" },
      stages: [
        { stage: "derivation", at: "2026-09-26T12:00:00+00:00", detail: {} },
        { stage: "failed", at: "2026-09-26T12:00:01+00:00", detail: { stage: "derivation" } },
      ],
    });
    const status = await getRetrogradeStatus(5);
    expect(retrogradeStageOf(status)).toBe("derivation");
    expect(status.stages.map((record) => record.stage)).toEqual(["derivation", "failed"]);
  });

  it.each([
    {
      name: "running packet with derivation recorded",
      stage: "packet",
      run_status: "running",
      detail: {},
      recorded: ["derivation", "packet"],
      skipped: [],
    },
    {
      name: "running packet without derivation",
      stage: "packet",
      run_status: "running",
      detail: {},
      recorded: ["packet"],
      skipped: ["derivation"],
    },
    {
      name: "done with every stage recorded",
      stage: "done",
      run_status: "done",
      detail: {},
      recorded: ["derivation", "packet", "seed_candidates", "expansion", "persistence", "embedding", "done"],
      skipped: [],
    },
    {
      name: "done idle with only derivation recorded",
      stage: "idle",
      run_status: "done",
      detail: {},
      recorded: ["derivation"],
      skipped: ["packet", "seed_candidates", "expansion", "persistence", "embedding"],
    },
    {
      name: "done idle without pipeline records",
      stage: "idle",
      run_status: "done",
      detail: {},
      recorded: [],
      skipped: ["derivation", "packet", "seed_candidates", "expansion", "persistence", "embedding"],
    },
    {
      name: "failed seed selection with its earlier records",
      stage: "failed",
      run_status: "failed",
      detail: { stage: "seed_candidates" },
      recorded: ["derivation", "packet", "seed_candidates", "failed"],
      skipped: [],
    },
    {
      name: "failed before any stage",
      stage: "idle",
      run_status: "failed",
      detail: {},
      recorded: [],
      skipped: [],
    },
  ])("derives skipped stages from the ledger: $name", async (scenario) => {
    serve({
      ...RECORD,
      stage: scenario.stage,
      run_status: scenario.run_status,
      error: scenario.run_status === "failed" ? "Stage failed" : null,
      detail: scenario.detail,
      stages: scenario.recorded.map((stage) => ({
        stage,
        at: "2026-09-26T12:00:00+00:00",
        detail: stage === "failed" ? scenario.detail : {},
      })),
    });
    expect(skippedRetrogradeStages(await getRetrogradeStatus(5))).toEqual(scenario.skipped);
  });

  it.each([
    [{ ...RECORD, run: null, run_status: null, stage: "idle", stages: [] }],
    [{ ...RECORD, run_status: "done", stage: "done", detail: { embedded_summaries: 2 }, stages: [] }],
  ])("places an idle or finished run at no stage (%j)", async (body) => {
    serve(body);
    expect(retrogradeStageOf(await getRetrogradeStatus(5))).toBeNull();
  });

  it("carries the run identity and the nexus.toml poll interval with each status", async () => {
    serve({ ...RECORD, status_poll_interval_seconds: 1.5, stage: "packet", detail: {}, stages: [] });
    const status = await getRetrogradeStatus(5);
    expect(status.run).toBe("run-of-this-transition");
    expect(status.status_poll_interval_seconds).toBe(1.5);
  });

  it.each([
    [{ ...RECORD, stage: "weaving", detail: {}, stages: [] }, "Unrecognized Retrograde status"],
    [{ ...RECORD, stage: "packet", detail: {} }, "Unrecognized Retrograde status"],
    [{ slot: 5, status_poll_interval_seconds: 1, stage: "packet", detail: {}, stages: [] }, "Unrecognized Retrograde status"],
    [{ ...RECORD, run: 7, stage: "packet", detail: {}, stages: [] }, "Unrecognized Retrograde status"],
    [{ ...RECORD, run_status: "failed", error: "Failed", stage: "failed", detail: {}, stages: [] }, "Retrograde failure names no known stage"],
    [{ ...RECORD, run_status: "failed", error: "Failed", stage: "failed", detail: { stage: "done" }, stages: [] }, "Retrograde failure names no known stage"],
  ])("rejects a malformed status %j", async (body, message) => {
    serve(body);
    await expect(getRetrogradeStatus(5)).rejects.toThrow(message);
  });

  it("rejects a record missing run_status", async () => {
    const { run_status: _status, ...record } = RECORD;
    serve({ ...record, stage: "packet", detail: {}, stages: [] });
    await expect(getRetrogradeStatus(5)).rejects.toThrow("Unrecognized Retrograde status");
  });

  it.each([
    { ...RECORD, run: null },
    { ...RECORD, run_status: null },
    { ...RECORD, error: "unexpected" },
    { ...RECORD, run_status: "failed", error: null },
    { ...RECORD, run_status: "unknown" },
  ])("rejects inconsistent run metadata %j", async (record) => {
    serve({ ...record, stage: "idle", stages: [] });
    await expect(getRetrogradeStatus(5)).rejects.toThrow("Unrecognized Retrograde status");
  });

  it("surfaces an HTTP failure", async () => {
    serve({ detail: "Internal Server Error" }, 500);
    await expect(getRetrogradeStatus(5)).rejects.toThrow("500:");
  });

  it.each([[undefined], [0], [-1], ["1"]])(
    "rejects a missing or non-positive poll interval (%j)",
    async (seconds) => {
      serve({ ...RECORD, status_poll_interval_seconds: seconds, stage: "idle", stages: [] });
      await expect(getRetrogradeStatus(5)).rejects.toThrow(
        "nexus.toml [orrery.retrograde.wizard] status_poll_interval_seconds must be a positive number",
      );
    },
  );

  it("ships a positive poll interval in nexus.toml", () => {
    const toml = readFileSync(resolve(dirname(ORCHESTRATOR), "../../../nexus.toml"), "utf-8");
    const section = toml.split(/^\[orrery\.retrograde\.wizard\]$/m)[1]?.split(/^\[/m)[0];
    expect(section, "[orrery.retrograde.wizard] in nexus.toml").toBeDefined();
    const value = section!.match(/^status_poll_interval_seconds = ([0-9.]+)$/m);
    expect(value, "status_poll_interval_seconds").not.toBeNull();
    expect(Number(value![1])).toBeGreaterThan(0);
  });
});
