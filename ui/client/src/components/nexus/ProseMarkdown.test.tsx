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

  it("trims a half-typed rule so `--` never flashes as text", () => {
    expect(prepareRevealSource("Before.\n\n--")).not.toContain("-");
    const { container } = render(
      <ProseMarkdown text={"Before.\n\n--"} revealing />,
    );
    expect(container.textContent).not.toContain("-");
    expect(container.querySelector(".type-caret")).not.toBeNull();
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
});
