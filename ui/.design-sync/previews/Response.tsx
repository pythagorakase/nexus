import { Response } from "nexus-ui";

// Streaming-prose markdown: paragraphs, emphasis, and dialogue — the everyday
// storyteller output. Renders the Veil serif body with copper foreground.
export const Prose = () => (
  <div style={{ width: 600 }}>
    <Response>
      {[
        "Rain hammered the spire glass while Mira counted the seconds between thunderclaps. *Three days now*, and the flood had not crested.",
        "",
        "Below, the Tidewardens worked their skiffs through drowned streets, and the bell buoy tolled — once, then silence. Someone was out there, and they were not lighting a lantern.",
      ].join("\n")}
    </Response>
  </div>
);

// Structured markdown: a heading, an ordered list of branch consequences, and a
// blockquote of remembered dialogue — exercises the custom renderers.
export const Structured = () => (
  <div style={{ width: 600 }}>
    <Response>
      {[
        "## The Prince's Offer",
        "",
        "If you accept the writ of safe conduct:",
        "",
        "1. The Nosferatu lose their claim on you",
        "2. You owe the Spire a single unnamed favor",
        "3. Cassius will not forgive the debt",
        "",
        "> \"A favor to a Prince is a leash with no visible end.\"",
        "",
        "Choose carefully — this one does not reset.",
      ].join("\n")}
    </Response>
  </div>
);

// Mixed inline formatting and a small table — code spans, bold, and GFM tables
// all themed against Veil tokens.
export const Mixed = () => (
  <div style={{ width: 600 }}>
    <Response>
      {[
        "The Archivist's ledger lists the sealed vaults by their **ward sigils**. The clerk whispers the access phrase: `tide-and-ash`.",
        "",
        "| Vault | Sigil | Status |",
        "| --- | --- | --- |",
        "| Lower Archive | Drowned Crown | Sealed |",
        "| Reliquary | Salt Lantern | Open |",
        "| Counting Room | Iron Tally | Watched |",
      ].join("\n")}
    </Response>
  </div>
);
