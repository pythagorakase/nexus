import { MapPlaceDialog } from "nexus-ui";

// Read-only place dossier modal. Rendered open. The portrait image comes from
// a headless /api/places/:id/images fetch that returns empty, so no <img>
// mounts — the dialog shows its metadata strip + the long-form prose sections
// from the (mocked) places row. We pass modal-less open so the bg overlay
// doesn't black the cell out.

const PLACE = {
  id: 314,
  name: "The Cinder Concourse",
  type: "district",
  zone: 7,
  summary:
    "A vaulted arcade of brass and smoked glass at the heart of the lower spire, where the gaslight never fully dies and the floor hums with the orrery turning beneath it.",
  inhabitants: ["The Archivist", "Mira Vale", "Lamplighters' Guild"],
  history:
    "Built over the ashes of the third Conflagration, the Concourse was meant as a memorial and became a market instead — grief and commerce sharing the same cold marble.",
  currentStatus:
    "Quiet at this hour. A single gear turns in the orrery; the Archivist keeps his post by the brass armature.",
  secrets:
    "The sealed envelope in the Archivist's drawer carries a name the Veil was paid to erase.",
  extraData: null,
  createdAt: "2026-06-01T00:00:00Z",
  updatedAt: "2026-06-01T00:00:00Z",
  coordinates: null,
  geom: null,
  // ST_AsGeoJSON Point, [longitude, latitude] order.
  geometry: { type: "Point", coordinates: [-0.1276, 51.5072] },
} as never;

const ZONE = {
  id: 7,
  name: "The Lower Spire",
  summary: "The industrial underbelly of the city, terraced into the old caldera.",
  boundary: null,
} as never;

const noop = () => {};

// Full dossier: type eyebrow, title, zone + coordinates meta, the glyph
// divider, and every prose section (summary / history / current status /
// inhabitants / secrets).
export const Open = () => (
  <div style={{ position: "relative", minHeight: 620 }}>
    <MapPlaceDialog
      place={PLACE}
      zone={ZONE}
      slot={2}
      open
      onOpenChange={noop}
    />
  </div>
);
