/**
 * DevMarkdownPreview - dev-only harness for narrative markdown rendering.
 *
 * Registered at /dev/markdown only when import.meta.env.DEV (see App.tsx).
 * Feeds a real save_02 legacy-corpus excerpt (narrative_chunks id 1425) and a
 * replayable typewriter reveal through the exact components and markup
 * NarrativePane uses (.reader / .prose-block / .md-part), so heading scale,
 * voice color, emphasis, and mid-reveal stabilization can be verified in a
 * real browser without staging database state.
 */
import { useState } from "react";
import { ProseMarkdown } from "@/components/nexus/ProseMarkdown";
import { TypewriterText } from "@/components/nexus/TypewriterText";
import "@/components/nexus/nexus-layout.css";

const LEGACY_EXCERPT = `<!-- SCENE BREAK: S05E06_001 (episode heading) -->
# S05E06: Extraction
## Storyteller
### **Sullivan Retrieval Mission**
\u{1F4CD} The Morning After | *Le Chat Noir*

The **morning air in New Orleans is thick with humidity, but it carries the scent of fresh beignets, chicory coffee, and the distant pulse of the river.**

The crew **moves through the quiet streets, recovering from the night before—some more gracefully than others.**

---

### **Crew Status Update**

- **Alex & Emilia** → _Well-rested, smug, and walking just a little too in sync._

- **Pete** → _Surprisingly un-hungover, but moving with the energy of a man whose worldview permanently shifted overnight._

> A quiet aside, the way the corpus actually quotes its asides.

#### Deep Heading Floor Check

Plain body prose stays upright; only *marked* spans italicize and only **marked** spans embolden.`;

const REVEAL_TEXT = `## Arrival

The dory knocks against the quay, the *Gullwise* riding low, and somewhere behind the fog a bell counts what the **harbor refuses to say out loud**.

You hold the lamp steady.`;

export default function DevMarkdownPreview() {
  const [run, setRun] = useState(1);
  return (
    <div style={{ padding: 28, background: "var(--bg)", minHeight: "100vh" }}>
      <article className="reader" data-testid="dev-markdown-reader">
        <div className="reader-frame">
          <div className="reader-inner">
            <section className="chunk-stream">
              <div className="chunk-block" data-testid="dev-md-committed">
                <div className="prose-block">
                  <div className="md-part st">
                    <ProseMarkdown text={LEGACY_EXCERPT} />
                  </div>
                  <hr className="voice-divider" />
                  <div className="md-part you">
                    <ProseMarkdown text="You take the ring — *not* to wear it, just to **hold the proof**." />
                  </div>
                </div>
              </div>
              <div className="chunk-block current" data-testid="dev-md-reveal">
                <div className="prose-block">
                  <div className="md-part st">
                    <TypewriterText
                      key={run}
                      text={REVEAL_TEXT}
                      msPerChar={18}
                      animate
                      markdown
                    />
                  </div>
                </div>
              </div>
            </section>
            <button
              type="button"
              className="choice"
              onClick={() => setRun((r) => r + 1)}
              data-testid="button-replay-reveal"
            >
              <span className="choice-glyph">◆</span>
              <span className="choice-text">Replay the reveal.</span>
            </button>
          </div>
        </div>
      </article>
    </div>
  );
}
