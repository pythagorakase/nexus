import { TypewriterText } from "nexus-ui";

// Presentational reveal component. animate=false renders the full text
// immediately (the live animation can't be captured in a still), so each
// cell shows the finished frame — identical to the committed-chunk render.

const PROSE =
  "The rain hadn't stopped for three days. Mira watched the spire lights bleed across the wet glass and counted the seconds between each roll of thunder.";

const MARKDOWN_PROSE = `The lift doors parted onto the **Cinder Concourse**, and the smell hit her first — ozone and burnt sugar.

*She had been here before,* in another life, before the Veil took her name.

> "You came back," the Archivist said, not looking up.`;

// Plain-text mode: a single styled span. The component owns no block layout
// here, so the wrapper supplies the reading typography.
export const PlainText = () => (
  <div
    className="md-part st"
    style={{
      maxWidth: 520,
      fontFamily: "var(--font-body, serif)",
      fontSize: 17,
      lineHeight: 1.7,
      color: "hsl(var(--foreground))",
    }}
  >
    <TypewriterText text={PROSE} msPerChar={35} animate={false} />
  </div>
);

// Markdown mode: the visible slice routes through ProseMarkdown, so emphasis,
// headings, and blockquotes are formatted mid-reveal. Block content can't live
// in a span, so the component returns the bare block stream — wrap it.
export const MarkdownMode = () => (
  <div
    className="reader-inner"
    style={{ maxWidth: 560, padding: "8px 0" }}
  >
    <div className="prose-block">
      <div className="md-part st">
        <TypewriterText
          text={MARKDOWN_PROSE}
          msPerChar={35}
          animate={false}
          markdown
        />
      </div>
    </div>
  </div>
);
