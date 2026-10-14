import { describe, expect, it } from "vitest";

import type { TraceEvidence, TraceNode } from "./types";
import { evidenceText, gateConsumesEvent } from "./vm";

function evidence(
  kind: string,
  observed: Record<string, unknown>,
  matched: unknown[] = [],
): TraceEvidence {
  return { kind, observed, matched, params: {}, entities: {}, result: true };
}

function leaf(raw: string): TraceNode {
  return { raw, prose: "hour gate", result: true };
}

describe("world-hour gate evidence", () => {
  it("shows elapsed world hours and absent occurrences", () => {
    expect(
      evidenceText(evidence("since_last_event_hours_at_least", { elapsed_hours: 1.5 })),
    ).toBe("1.5h ago");
    expect(
      evidenceText(evidence("since_last_event_hours_at_least", { elapsed_hours: null })),
    ).toBe("never fired");
  });

  it("counts matching occurrences in the world-hour window", () => {
    expect(
      evidenceText(evidence("recent_event_within_hours", {}, [{ event_id: 1 }, { event_id: 2 }])),
    ).toBe("2 in window");
    expect(evidenceText(evidence("recent_event_within_hours", {}))).toBe("none in window");
  });

  it.each([
    "recent_event_within_hours(stroll_taken,<=1.5h)",
    "since_last_event_hours_at_least(stroll_taken,1.5h@actor)",
  ])("exposes %s to the event lens", (raw) => {
    expect(gateConsumesEvent(leaf(raw), "stroll_taken")).toBe(true);
    expect(gateConsumesEvent(leaf(raw), "threat_issued")).toBe(false);
    expect(
      gateConsumesEvent({ ...leaf("AND(1)"), op: "AND", children: [leaf(raw)] }, "stroll_taken"),
    ).toBe(true);
  });
});
