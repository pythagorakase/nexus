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
import { InlineMarkdown, ProseMarkdown } from "./ProseMarkdown";

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
 * so the spans end in punctuation (`favor.*`).
 */
const SKALD_CHUNK_6_EXCERPT = `Odile’s summons is folded inside your coat, already soft from damp. Seven words in her cramped archive hand:

*Before first bell. Come alone. Last favor.*

Not *urgent*. Not *danger*. Odile Sorrenwick was born into a city where panic is taxed if spoken aloud.`;

/** Real Skald output from save_05 narrative_chunks id 7 (same capture). */
const SKALD_CHUNK_7_EXCERPT = `Somewhere below the Annex, below the seawall, below any lawful map of Veyport, a voice like water remembered under a door shapes your name with patient intimacy.

*Brena.*`;

describe("ProseMarkdown", () => {
  it("renders every paragraph immediately on mount and replacement", () => {
    const { container, rerender } = render(
      <ProseMarkdown text={SKALD_CHUNK_6_EXCERPT} />,
    );
    expect(container.querySelectorAll("p")).toHaveLength(3);
    expect(container.textContent).toContain("panic is taxed if spoken aloud.");
    expect(container.querySelector(".type-caret")).toBeNull();

    rerender(<ProseMarkdown text={SKALD_CHUNK_7_EXCERPT} />);
    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.querySelector("em")).toHaveTextContent("Brena.");
    expect(container.textContent).not.toContain("Odile");
    expect(container.querySelector(".type-caret")).toBeNull();
  });

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

describe("InlineMarkdown (choice labels)", () => {
  // No live chunk carries marked-up choices as of 2026-06-12 (verified
  // across save_01..save_05 choice_object->'presented'), so these fixtures
  // are pinned in the dialect the PR #386 survey documented for fresh Skald
  // output: sentence emphasis via single asterisks (the real chunk strings
  // `*Brena.*` / `*Before first bell. Come alone. Last favor.*`) and
  // `**bold**`.
  it("renders *emphasis* as <em> with no literal asterisks", () => {
    const { container } = render(
      <InlineMarkdown text="Answer her: *Before first bell. Come alone. Last favor.*" />,
    );
    const em = container.querySelector("em");
    expect(em).not.toBeNull();
    expect(em!.textContent).toBe("Before first bell. Come alone. Last favor.");
    expect(container.textContent).not.toContain("*");
  });

  it("renders **bold** as <strong> with no literal asterisks", () => {
    const { container } = render(
      <InlineMarkdown text="Refuse. **Walk away** before first bell." />,
    );
    const strong = container.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong!.textContent).toBe("Walk away");
    expect(container.textContent).not.toContain("*");
  });

  it("handles mixed emphasis exactly like prose rendering", () => {
    const { container } = render(
      <InlineMarkdown text="Hold the line while *Brena.* watches — **do not blink**." />,
    );
    expect(container.querySelector("em")!.textContent).toBe("Brena.");
    expect(container.querySelector("strong")!.textContent).toBe(
      "do not blink",
    );
    expect(container.textContent).not.toMatch(/[*_]/);
  });

  it("emits no block elements - paragraphs unwrap, headings flatten to text", () => {
    const { container } = render(<InlineMarkdown text="## Storm the gate" />);
    expect(
      container.querySelector("p, h1, h2, h3, ul, ol, blockquote, hr"),
    ).toBeNull();
    expect(container.textContent).toBe("Storm the gate");
  });

  it("unwraps links to their text - no navigation surface inside a choice", () => {
    const { container } = render(
      <InlineMarkdown text="Ask [Pete](https://example.com) to run the decoy." />,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe("Ask Pete to run the decoy.");
  });

  it("passes plain choices through untouched", () => {
    // Real choice string from save_02 (latest committed choice set).
    const real =
      "Disconnect the hard-line cleanly now and withdraw through the crawlspace before the technician reaches the annex door.";
    const { container } = render(<InlineMarkdown text={real} />);
    expect(container.textContent).toBe(real);
  });
});
