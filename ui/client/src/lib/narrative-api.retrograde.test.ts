import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RETROGRADE_STAGES,
  getRetrogradeStatus,
  retrogradeStageOf,
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
