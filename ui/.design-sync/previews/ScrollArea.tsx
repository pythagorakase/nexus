import { ScrollArea, Separator } from "nexus-ui";

const chapters = [
  "Chapter 1 — The Tide Comes In",
  "Chapter 2 — Salt and Static",
  "Chapter 3 — The Archivist's Door",
  "Chapter 4 — Lanterns Below",
  "Chapter 5 — What the Water Kept",
  "Chapter 6 — A Name in the Ledger",
  "Chapter 7 — The Drowned Choir",
  "Chapter 8 — Glass and Grief",
  "Chapter 9 — The Long Descent",
  "Chapter 10 — Where the Maps End",
  "Chapter 11 — Cassius Returns",
  "Chapter 12 — The Last Dry Room",
];

// A tall chapter list constrained to a fixed-height scroll viewport.
export const ChapterList = () => (
  <ScrollArea
    style={{ height: 220, width: 300, border: "1px solid hsl(var(--border))", borderRadius: 8 }}
  >
    <div style={{ padding: 16 }}>
      <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 10 }}>Chapters</div>
      {chapters.map((c, i) => (
        <div key={c}>
          <div style={{ padding: "8px 0", fontSize: 14 }}>{c}</div>
          {i < chapters.length - 1 && <Separator />}
        </div>
      ))}
    </div>
  </ScrollArea>
);

// Scrolling a long block of narrative prose.
export const ProseScroll = () => (
  <ScrollArea
    style={{ height: 200, width: 360, border: "1px solid hsl(var(--border))", borderRadius: 8 }}
  >
    <div style={{ padding: 16, fontSize: 14, lineHeight: 1.6 }}>
      <p style={{ marginTop: 0 }}>
        The rain hadn't stopped for three days. Mira watched the spire lights
        bleed across the wet glass and counted the seconds between thunder.
      </p>
      <p>
        Below the waterline, the old archive still hummed. Someone had kept the
        lamps burning long after the city above forgot the rooms existed.
      </p>
      <p>
        Cassius said the ledgers remembered everything — every name, every debt,
        every promise the tide had swallowed. She hadn't believed him until the
        door answered to a name she'd never spoken aloud.
      </p>
      <p style={{ marginBottom: 0 }}>
        Now the choir was singing again, somewhere past the last dry room, and
        the water was rising to meet it.
      </p>
    </div>
  </ScrollArea>
);
