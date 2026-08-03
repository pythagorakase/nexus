import { Intertitle } from "nexus-ui";

// Quiet scene grounding. NarrativePane emits one only at a committed scene
// boundary — the first chunk, or wherever the season/episode/scene key changes.
// Pure props, no data binding, so every cell is the real component at a real
// boundary.
//
// Two fields carry the variation: `worldTime` is the calculated in-world
// timestamp (nullable — chunks before the first base_timestamp have none), and
// the layer suffix appears only for a non-"primary" world_layer. The schema
// admits exactly two layers, 'primary' and 'retrograde'.

const READER = { maxWidth: 560 };

// Canonical boundary: primary layer, world clock resolved. The timestamp
// formats as "14 Mar 2073 · 21:40".
export const SceneBoundary = () => (
  <div style={READER}>
    <Intertitle
      season={1}
      episode={2}
      scene={3}
      worldLayer="primary"
      worldTime="2073-03-14T21:40"
    />
  </div>
);

// No world clock: the slug line stands alone, and the divider still carries the
// boundary. This is the state every chunk shows before a base_timestamp is set.
export const WithoutWorldTime = () => (
  <div style={READER}>
    <Intertitle
      season={1}
      episode={1}
      scene={1}
      worldLayer="primary"
      worldTime={null}
    />
  </div>
);

// Retrograde layer: summaries held out of narrative continuity are stamped with
// a non-primary world_layer, and the slug picks up the layer suffix so the
// boundary reads as off-spine.
export const RetrogradeLayer = () => (
  <div style={READER}>
    <Intertitle
      season={2}
      episode={7}
      scene={12}
      worldLayer="retrograde"
      worldTime="2071-11-02T04:15"
    />
  </div>
);
