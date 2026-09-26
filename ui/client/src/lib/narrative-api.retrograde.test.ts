import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RETROGRADE_STAGES,
  getRetrogradeStatus,
  getRetrogradeStatusPollSeconds,
  retrogradeStageOf,
} from "./narrative-api";

const ORCHESTRATOR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../../nexus/agents/orrery/retrograde_orchestrator.py",
);

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
      slot: 5,
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
    serve({ slot: 5, stage: "failed", detail: { stage: "embedding" }, stages: [] });
    expect(retrogradeStageOf(await getRetrogradeStatus(5))).toBe("embedding");
  });

  it.each([
    [{ slot: 5, stage: "idle", stages: [] }],
    [{ slot: 5, stage: "done", detail: { embedded_summaries: 2 }, stages: [] }],
  ])("places an idle or finished run at no stage (%j)", async (body) => {
    serve(body);
    expect(retrogradeStageOf(await getRetrogradeStatus(5))).toBeNull();
  });

  it.each([
    [{ slot: 5, stage: "weaving", detail: {}, stages: [] }, "Unrecognized Retrograde status"],
    [{ slot: 5, stage: "packet", detail: {} }, "Unrecognized Retrograde status"],
    [{ slot: 5, stage: "failed", detail: {}, stages: [] }, "Retrograde failure names no known stage"],
    [{ slot: 5, stage: "failed", detail: { stage: "done" }, stages: [] }, "Retrograde failure names no known stage"],
  ])("rejects a malformed status %j", async (body, message) => {
    serve(body);
    await expect(getRetrogradeStatus(5)).rejects.toThrow(message);
  });

  it("surfaces an HTTP failure", async () => {
    serve({ detail: "Internal Server Error" }, 500);
    await expect(getRetrogradeStatus(5)).rejects.toThrow("500:");
  });

  it("reads the poll interval from nexus.toml through the settings payload", async () => {
    const fetch = serve({ orrery: { retrograde: { wizard: { status_poll_interval_seconds: 1.5 } } } });
    expect(await getRetrogradeStatusPollSeconds()).toBe(1.5);
    expect(fetch).toHaveBeenCalledWith("/api/settings");
  });

  it.each([[{ orrery: { retrograde: { wizard: {} } } }], [{ orrery: { retrograde: { wizard: { status_poll_interval_seconds: 0 } } } }]])(
    "rejects a missing or non-positive poll interval (%j)",
    async (body) => {
      serve(body);
      await expect(getRetrogradeStatusPollSeconds()).rejects.toThrow(
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
