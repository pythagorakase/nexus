/**
 * ProseMarkdown tests - real markdown rendering for the narrative reader.
 *
 * The legacy-corpus fixture below is real text captured from save_02
 * narrative_chunks id 1425 on 2026-06-12 (trailing hard-break spaces and
 * list-continuation indentation normalized for source hygiene). It exercises
 * the dialect the storyteller actually emits: h1 episode headings, h2 voice
 * headings, h3 section headings with bold inside, **bold**, *italic*,
 * _italic_, `---` rules, bullet lists, and HTML scene-break comments.
 */
import { render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ProseMarkdown, prepareRevealSource } from "./ProseMarkdown";
import { TypewriterText } from "./TypewriterText";

const LEGACY_CHUNK_1425_EXCERPT = `<!-- SCENE BREAK: S05E06_001 (episode heading) -->
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
`;

/**
 * Real Skald output captured from save_05 narrative_chunks id 6 on
 * 2026-06-12. Fresh chunks italicize whole sentences with single asterisks,
 * so the spans end in punctuation (`favor.*`) - the form that regressed
 * during typewriter reveal when a sentinel character followed the closing
 * delimiter and broke CommonMark's right-flanking rule.
 */
const SKALD_CHUNK_6_EXCERPT = `Odile’s summons is folded inside your coat, already soft from damp. Seven words in her cramped archive hand:

*Before first bell. Come alone. Last favor.*

Not *urgent*. Not *danger*. Odile Sorrenwick was born into a city where panic is taxed if spoken aloud.`;

/** Real Skald output from save_05 narrative_chunks id 7 (same capture). */
const SKALD_CHUNK_7_EXCERPT = `Somewhere below the Annex, below the seawall, below any lawful map of Veyport, a voice like water remembered under a door shapes your name with patient intimacy.

*Brena.*`;

describe("ProseMarkdown", () => {
  it("renders **bold** as <strong> with no literal asterisks", () => {
    const { container } = render(<ProseMarkdown text="A **bold** claim." />);
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong!.textContent).toBe("bold");
    expect(container.textContent).not.toContain("*");
  });

  it("renders *italic* and _italic_ as <em>", () => {
    const { container } = render(
      <ProseMarkdown text="The *Gullwise* knocks; _witnessed_ and sealed." />,
    );
    const ems = container.querySelectorAll("em");
    expect(ems).toHaveLength(2);
    expect(ems[0].textContent).toBe("Gullwise");
    expect(ems[1].textContent).toBe("witnessed");
    expect(container.textContent).not.toContain("*");
    expect(container.textContent).not.toContain("_");
  });

  it("leaves body prose as plain text nodes (no italic-everything wrapper)", () => {
    const { container } = render(
      <ProseMarkdown text="Plain prose stays upright." />,
    );
    expect(container.querySelector("em")).toBeNull();
    expect(container.querySelector("p.line")).not.toBeNull();
  });

  it("renders ## as h2.md-h2 and ### as h3.md-h3", () => {
    const { container } = render(
      <ProseMarkdown text={"## Storyteller\n\n### Section"} />,
    );
    expect(container.querySelector("h2.md-h2")!.textContent).toBe(
      "Storyteller",
    );
    expect(container.querySelector("h3.md-h3")!.textContent).toBe("Section");
    expect(container.textContent).not.toContain("#");
  });

  it("clamps an in-content h1 to the h2 treatment", () => {
    const { container } = render(
      <ProseMarkdown text="# S05E06: Extraction" />,
    );
    expect(container.querySelector("h1")).toBeNull();
    const clamped = container.querySelector("h2.md-h2");
    expect(clamped).not.toBeNull();
    expect(clamped!.textContent).toBe("S05E06: Extraction");
  });

  it("floors h4-h6 at the h4 (body-size) treatment", () => {
    const { container } = render(
      <ProseMarkdown text={"#### Four\n\n##### Five\n\n###### Six"} />,
    );
    expect(container.querySelectorAll(".md-h4")).toHaveLength(3);
  });

  it("renders --- as a styled rule, lists, and blockquotes", () => {
    const { container } = render(
      <ProseMarkdown
        text={"Before.\n\n---\n\n- one\n- two\n\n> a quiet aside"}
      />,
    );
    expect(container.querySelector("hr.md-hr")).not.toBeNull();
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelector("blockquote")!.textContent).toContain(
      "a quiet aside",
    );
  });

  it("drops raw HTML (scene-break comments) without rendering it", () => {
    const { container } = render(
      <ProseMarkdown
        text={"<!-- SCENE BREAK: S05E06_001 -->\nThe fog comes in low."}
      />,
    );
    expect(container.textContent).not.toContain("SCENE BREAK");
    expect(container.textContent).toContain("The fog comes in low.");
  });

  it("renders links as plain text without an anchor", () => {
    const { container } = render(
      <ProseMarkdown text="See [the ledger](https://example.com)." />,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("the ledger");
  });

  it("never emits an <img>; image markdown renders alt text only", () => {
    const { container } = render(
      <ProseMarkdown text="Before ![a tracking pixel](https://example.com/p.png) after." />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("a tracking pixel");
    const { container: noAlt } = render(
      <ProseMarkdown text="Bare ![](https://example.com/p.png) image." />,
    );
    expect(noAlt.querySelector("img")).toBeNull();
    expect(noAlt.textContent).toContain("Bare");
  });

  it("renders the real save_02 legacy excerpt cleanly", () => {
    const { container } = render(
      <ProseMarkdown text={LEGACY_CHUNK_1425_EXCERPT} />,
    );
    // Heading clamp + hierarchy.
    expect(container.querySelector("h1")).toBeNull();
    const h2s = container.querySelectorAll("h2.md-h2");
    expect(h2s.length).toBe(2); // clamped episode heading + voice heading
    expect(h2s[0].textContent).toBe("S05E06: Extraction");
    expect(container.querySelectorAll("h3.md-h3").length).toBe(2);
    // Bold and italics resolved, no leaked syntax.
    expect(container.querySelectorAll("strong").length).toBeGreaterThan(3);
    expect(container.querySelectorAll("em").length).toBeGreaterThan(1);
    expect(container.textContent).not.toContain("*");
    expect(container.textContent).not.toContain("##");
    expect(container.textContent).not.toContain("SCENE BREAK");
    expect(container.textContent).not.toContain("---");
    // Structure: rule + list survived.
    expect(container.querySelector("hr.md-hr")).not.toBeNull();
    expect(container.querySelectorAll("ul li").length).toBe(2);
  });

  it("renders real Skald sentence-italics (save_05 chunk 6) as <em>", () => {
    const { container } = render(
      <ProseMarkdown text={SKALD_CHUNK_6_EXCERPT} />,
    );
    const ems = Array.from(container.querySelectorAll("em")).map(
      (em) => em.textContent,
    );
    expect(ems).toEqual([
      "Before first bell. Come alone. Last favor.",
      "urgent",
      "danger",
    ]);
    expect(container.textContent).not.toContain("*");
  });
});

describe("heading scale (nexus-layout.css)", () => {
  const css = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "nexus-layout.css"),
    "utf-8",
  );

  function sizeOf(selector: string): number {
    const pattern = new RegExp(
      `${selector.replace(/[.\\]/g, "\\$&")}[^}]*font-size:\\s*(\\d+(?:\\.\\d+)?)px`,
    );
    const match = css.match(pattern);
    expect(match, `font-size for ${selector}`).not.toBeNull();
    return parseFloat(match![1]);
  }

  it("keeps body prose upright by stylesheet", () => {
    const line = css.match(/\.prose-block \.line \{[^}]*\}/);
    expect(line).not.toBeNull();
    expect(line![0]).toContain("font-style: normal");
  });

  it("sizes h2 at ~1.25-1.4x body so chrome still dominates", () => {
    const body = sizeOf(".prose-block .line");
    const h2 = sizeOf(".prose-block .md-h2");
    expect(h2 / body).toBeGreaterThanOrEqual(1.25);
    expect(h2 / body).toBeLessThanOrEqual(1.4);
  });

  it("steps h3 down from h2 but never below body", () => {
    const body = sizeOf(".prose-block .line");
    const h2 = sizeOf(".prose-block .md-h2");
    const h3 = sizeOf(".prose-block .md-h3");
    expect(h3).toBeLessThan(h2);
    expect(h3).toBeGreaterThanOrEqual(body);
  });

  it("floors h4 at exactly body size", () => {
    const body = sizeOf(".prose-block .line");
    const h3 = sizeOf(".prose-block .md-h3");
    const h4 = sizeOf(".prose-block .md-h4");
    expect(h4).toBeLessThanOrEqual(h3);
    expect(h4).toBeGreaterThanOrEqual(body);
  });
});

describe("typewriter reveal", () => {
  it("renders the finished frame as full markdown (no swap needed)", () => {
    const { container } = render(
      <TypewriterText
        text={"## Arrival\n\nA **bold** *entrance*."}
        msPerChar={1}
        animate={false}
        markdown
      />,
    );
    expect(container.querySelector("h2.md-h2")!.textContent).toBe("Arrival");
    expect(container.querySelector("strong")!.textContent).toBe("bold");
    expect(container.querySelector("em")!.textContent).toBe("entrance");
    expect(container.textContent).not.toContain("*");
    expect(container.querySelector(".type-caret")).toBeNull();
  });

  it("closes dangling bold mid-reveal and rides the caret inline", () => {
    const { container } = render(
      <ProseMarkdown text="The crew **moves thro" revealing />,
    );
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong!.textContent).toContain("moves thro");
    expect(container.textContent).not.toContain("*");
    // Caret is injected inside the in-progress emphasis, at the frontier.
    expect(strong!.querySelector(".type-caret")).not.toBeNull();
  });

  it("closes dangling _italic_ mid-reveal (legacy underscore emphasis)", () => {
    const { container } = render(
      <ProseMarkdown text="Alex is _well-rest" revealing />,
    );
    const em = container.querySelector("em");
    expect(em).not.toBeNull();
    expect(em!.textContent).toContain("well-rest");
    expect(container.textContent).not.toContain("_");
  });

  it("trims a half-typed rule so `--` never flashes as text", () => {
    expect(prepareRevealSource("Before.\n\n--")).not.toContain("-");
    const { container } = render(
      <ProseMarkdown text={"Before.\n\n--"} revealing />,
    );
    expect(container.textContent).not.toContain("-");
    expect(container.querySelector(".type-caret")).not.toBeNull();
  });

  it("trims longer CommonMark rule variants up to six markers", () => {
    expect(prepareRevealSource("Before.\n\n-----")).not.toContain("-");
    expect(prepareRevealSource("Before.\n\n------")).not.toContain("-");
  });

  it("trims bare heading hashes until their text arrives", () => {
    const { container } = render(
      <ProseMarkdown text={"Seen.\n\n##"} revealing />,
    );
    expect(container.textContent).not.toContain("#");
  });

  it("never leaks the caret sentinel as text", () => {
    const { container } = render(
      <ProseMarkdown text="Mid-sentence revea" revealing />,
    );
    expect(container.textContent).not.toContain("\uE000");
    expect(container.querySelector(".type-caret")).not.toBeNull();
  });

  // Regression (user report: "*italic* not rendering"): the frame whose
  // last typed character is the closing `*` of a punctuation-final span.
  // The old in-source caret sentinel (a word character to micromark) made
  // that closing delimiter non-right-flanking, so the whole span flashed
  // as literal asterisks at the exact moment it completed.
  it("keeps a just-completed punctuation-final *italic* span italic mid-reveal", () => {
    const end =
      SKALD_CHUNK_6_EXCERPT.indexOf("Last favor.*") + "Last favor.*".length;
    const { container } = render(
      <ProseMarkdown text={SKALD_CHUNK_6_EXCERPT.slice(0, end)} revealing />,
    );
    const em = container.querySelector("em");
    expect(em).not.toBeNull();
    expect(em!.textContent).toContain("Before first bell. Come alone.");
    expect(container.textContent).not.toContain("*");
    expect(container.querySelector(".type-caret")).not.toBeNull();
  });

  it("keeps just-completed **bold.** and _italic._ spans styled mid-reveal", () => {
    const bold = render(
      <ProseMarkdown text={'He says **"Stop."**'} revealing />,
    );
    expect(bold.container.querySelector("strong")!.textContent).toBe(
      '"Stop."',
    );
    expect(bold.container.textContent).not.toContain("*");
    const under = render(
      <ProseMarkdown
        text="- **Pete** \u2192 _Surprisingly un-hungover, but moving with the energy of a man whose worldview permanently shifted overnight._"
        revealing
      />,
    );
    expect(under.container.querySelector("em")!.textContent).toContain(
      "Surprisingly un-hungover",
    );
    expect(under.container.textContent).not.toContain("_");
  });

  it("renders a just-typed opener as plain text, not an empty emphasis", () => {
    // Frame ends exactly on the opening `*` of mid-line `*urgent*`: closing
    // it would yield the empty-emphasis literal `Not **`. The trailing run
    // is stripped instead; the opener reappears with its first content char.
    const opener = render(<ProseMarkdown text="Not *" revealing />);
    expect(opener.container.textContent).not.toContain("*");
    expect(opener.container.querySelector(".type-caret")).not.toBeNull();
    const boldOpener = render(<ProseMarkdown text="the **" revealing />);
    expect(boldOpener.container.textContent).not.toContain("*");
  });

  it("rebuilds a half-typed closing run instead of leaking stars", () => {
    // One of the two closing stars typed: `**moves through...*`.
    const { container } = render(
      <ProseMarkdown text="The crew **moves through the quiet streets*" revealing />,
    );
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong!.textContent).toContain("moves through the quiet streets");
    expect(container.textContent).not.toContain("*");
  });

  it("never flashes literal markers on any frame of a real reveal", () => {
    // Sweeps every typewriter frame of real corpus text: fresh Skald
    // sentence-italics (save_05), a bold legacy line, and the full legacy
    // excerpt whose scene-break comment contains `_` (which must not count
    // toward delimiter parity - skipHtml drops the comment, so a parity
    // closer would ride the caret as a literal underscore forever).
    const texts = [
      `${SKALD_CHUNK_7_EXCERPT}\n\nThe lower stacks answer.`,
      SKALD_CHUNK_6_EXCERPT,
      "The crew **moves through the quiet streets, recovering from the night before—some more gracefully than others.**\n\nDone.",
      LEGACY_CHUNK_1425_EXCERPT,
    ];
    for (const text of texts) {
      for (let frontier = 1; frontier <= text.length; frontier += 1) {
        const { container, unmount } = render(
          <ProseMarkdown text={text.slice(0, frontier)} revealing />,
        );
        expect(
          container.textContent,
          `literal marker leaked at frame ${frontier} of ${JSON.stringify(text.slice(0, 30))}`,
        ).not.toMatch(/[*_]/);
        unmount();
      }
    }
  });

  it("renders the live *Brena.* paragraph italic with the caret inside", () => {
    const { container } = render(
      <ProseMarkdown text={SKALD_CHUNK_7_EXCERPT} revealing />,
    );
    const ems = container.querySelectorAll("em");
    expect(ems).toHaveLength(1);
    expect(ems[0].textContent).toContain("Brena.");
    expect(container.textContent).not.toContain("*");
    expect(container.querySelector(".type-caret")).not.toBeNull();
  });
});
