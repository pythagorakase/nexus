import { Textarea, Label } from "nexus-ui";

// Labeled prose input with a realistic placeholder — the player's free-text turn.
export const PlayerAction = () => (
  <div style={{ width: 460, display: "flex", flexDirection: "column", gap: 8 }}>
    <Label htmlFor="action">Your Action</Label>
    <Textarea
      id="action"
      style={{ minHeight: 120 }}
      placeholder="Describe what Mira does next — climb toward the spire lights, or wait for Cassius at the gate…"
    />
  </div>
);

// Filled state: a written seed paragraph for a new story.
export const StorySeed = () => (
  <div style={{ width: 460, display: "flex", flexDirection: "column", gap: 8 }}>
    <Label htmlFor="seed">Opening Seed</Label>
    <Textarea
      id="seed"
      style={{ minHeight: 120 }}
      defaultValue={
        "A drowned coastal city where the rain never stops. Mira, an archivist's apprentice, has spent three days tracking the spire lights that bleed across the flooded glass."
      }
    />
  </div>
);

// Disabled state — read-only while the chapter is committing.
export const Locked = () => (
  <div style={{ width: 460, display: "flex", flexDirection: "column", gap: 8 }}>
    <Label htmlFor="locked">Your Action (Committing Chapter…)</Label>
    <Textarea
      id="locked"
      style={{ minHeight: 100 }}
      defaultValue="Mira steps onto the flooded stair and reaches for the railing."
      disabled
    />
  </div>
);
