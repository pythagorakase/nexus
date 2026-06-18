import { ProseMarkdown, InlineMarkdown } from "nexus-ui";

// Real markdown rendering for narrative prose. Sizing for headings/rules/
// lists lives in nexus-layout.css (.md-heading / .md-hr / .line), keyed off
// the .reader-inner > .prose-block > .md-part context the reader supplies.

const STORY = `## The Cinder Concourse

The lift doors parted onto the concourse, and the smell hit her first — **ozone and burnt sugar**, the perfume of a city that never quite finished burning.

*She had been here before.* In another life, before the Veil took her name and gave her this one instead.

The Archivist waited by the brass orrery, turning a single gear with one finger.

- He never looked up when she entered.
- He never had to.
- The room told him everything.

> "You came back," he said. "They always do."

---

She crossed the floor, and the gaslight followed her like a held breath.`;

// Full prose block: heading clamp, bold/italic emphasis, an unordered list,
// a blockquote, and a horizontal rule — the full corpus dialect.
export const Narrative = () => (
  <div className="reader-inner" style={{ maxWidth: 600 }}>
    <div className="prose-block">
      <div className="md-part st">
        <ProseMarkdown text={STORY} />
      </div>
    </div>
  </div>
);

// Two-voice render: storyteller prose in warm cream, the player's recorded
// response in muted cream, separated by the centered voice divider — exactly
// how the reader composes a committed chunk.
export const TwoVoices = () => (
  <div className="reader-inner" style={{ maxWidth: 600 }}>
    <div className="prose-block">
      <div className="md-part st">
        <ProseMarkdown text="The Archivist slid a sealed envelope across the desk. *Your name is inside,* he said. *The old one.*" />
      </div>
      <hr className="voice-divider" />
      <div className="md-part you">
        <ProseMarkdown text="I leave the envelope where it lies. **I don't need the name he's selling.**" />
      </div>
    </div>
  </div>
);

// Inline-only variant for choice labels: emphasis/strong render, every block
// construct is unwrapped to plain text so a stray marker can't break a button.
export const InlineChoice = () => (
  <section className="choices" style={{ maxWidth: 560 }}>
    <button className="choice">
      <span className="choice-key">1</span>
      <span className="choice-glyph">◆</span>
      <span className="choice-text">
        <InlineMarkdown text="Open the envelope and read your **true name**." />
      </span>
    </button>
    <button className="choice">
      <span className="choice-key">2</span>
      <span className="choice-glyph">◆</span>
      <span className="choice-text">
        <InlineMarkdown text="*Refuse.* Walk back into the rain." />
      </span>
    </button>
  </section>
);
