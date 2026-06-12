/**
 * ProseMarkdown - real markdown rendering for narrative prose.
 *
 * Replaces the old single-asterisk regex in NarrativePane (which italicized
 * whole passages and leaked literal `**` / `##` markers). Parses the dialect
 * Skald and the imported legacy corpus actually emit: `**bold**`, `*italic*`
 * and `_italic_`, `#`-`######` ATX headings, `---` rules, `-`/`1.` lists,
 * `>` blockquotes, and hard line breaks (GFM).
 *
 * Safety: raw HTML is never rendered (react-markdown default) and is dropped
 * entirely via `skipHtml` so legacy `<!-- SCENE BREAK -->` comments vanish
 * instead of printing literally. Links render as plain styled text - no
 * navigation surface inside narrative. No dangerouslySetInnerHTML anywhere.
 *
 * Heading clamp: `#` in chunk content renders with the h2 treatment, and
 * h4-h6 floor at the h4 treatment (body size). Sizing lives in
 * nexus-layout.css (.md-h2 / .md-h3 / .md-h4).
 *
 * Reveal mode (`revealing`) supports the typewriter: the partial text is
 * stabilized (dangling `**` / `*` closed, half-typed marker lines trimmed) so
 * markdown renders correctly mid-reveal without flashing literal syntax, and
 * an inline caret element is injected at the reveal frontier via a tiny
 * rehype plugin.
 */
import ReactMarkdown, { type Options } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Element, ElementContent, Root, Text } from "hast";

/** Private-use sentinel marking the reveal frontier; never user-visible. */
const CARET_SENTINEL = "\uE000";

const components: Options["components"] = {
  // Clamp: an in-chunk h1 gets the h2 treatment.
  h1: ({ children }) => <h2 className="md-heading md-h2">{children}</h2>,
  h2: ({ children }) => <h2 className="md-heading md-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="md-heading md-h3">{children}</h3>,
  // Floor: h4 and deeper never render smaller than body text.
  h4: ({ children }) => <h4 className="md-heading md-h4">{children}</h4>,
  h5: ({ children }) => <h5 className="md-heading md-h4">{children}</h5>,
  h6: ({ children }) => <h6 className="md-heading md-h4">{children}</h6>,
  p: ({ children }) => <p className="line">{children}</p>,
  hr: () => <hr className="md-hr" />,
  // Narrative carries no navigation: render link text, drop the href.
  a: ({ children }) => <span className="md-link">{children}</span>,
};

/**
 * Close dangling emphasis markers in a partially revealed markdown string so
 * the typewriter shows `**bo` as bold-in-progress rather than literal stars.
 * Returns the suffix of closing markers to append (after the caret).
 */
function emphasisClosers(partial: string): string {
  let closers = "";
  const boldTokens = (partial.match(/\*\*/g) ?? []).length;
  if (boldTokens % 2 === 1) closers += "**";
  const singleStars = (partial.replace(/\*\*/g, "").match(/\*/g) ?? []).length;
  if (singleStars % 2 === 1) closers += "*";
  return closers;
}

/**
 * Build the markdown source for a mid-reveal frame: trim a trailing line
 * that is still just structural markers (`--` typing toward `---`, bare
 * `##`, `>`), insert the caret sentinel at the frontier, and close any
 * dangling emphasis after it.
 */
export function prepareRevealSource(partial: string): string {
  const trimmed = partial.replace(/(^|\n)[-*_#>]{1,4}[ \t]*$/, "$1");
  return trimmed + CARET_SENTINEL + emphasisClosers(trimmed);
}

/** Replace the caret sentinel text with an inline caret element. */
function injectCaret(parent: Root | Element): boolean {
  for (let i = parent.children.length - 1; i >= 0; i -= 1) {
    const child = parent.children[i];
    if (child.type === "text" && child.value.includes(CARET_SENTINEL)) {
      const before = child.value.slice(0, child.value.indexOf(CARET_SENTINEL));
      const after = child.value.slice(
        child.value.indexOf(CARET_SENTINEL) + CARET_SENTINEL.length,
      );
      const caret: Element = {
        type: "element",
        tagName: "span",
        properties: { className: ["type-caret"], ariaHidden: "true" },
        children: [],
      };
      const replacement: ElementContent[] = [];
      if (before) replacement.push({ type: "text", value: before } as Text);
      replacement.push(caret);
      if (after) replacement.push({ type: "text", value: after } as Text);
      parent.children.splice(i, 1, ...replacement);
      return true;
    }
    if (child.type === "element" && injectCaret(child)) return true;
  }
  return false;
}

/** Strip any sentinel that survived in odd positions (defensive). */
function stripSentinels(parent: Root | Element): void {
  for (const child of parent.children) {
    if (child.type === "text" && child.value.includes(CARET_SENTINEL)) {
      child.value = child.value.split(CARET_SENTINEL).join("");
    } else if (child.type === "element") {
      stripSentinels(child);
    }
  }
}

function rehypeCaret() {
  return (tree: Root) => {
    injectCaret(tree);
    stripSentinels(tree);
  };
}

const REMARK_PLUGINS = [remarkGfm];
const REVEAL_REHYPE_PLUGINS = [rehypeCaret];

interface ProseMarkdownProps {
  text: string;
  /**
   * When true the text is a partial typewriter frame: dangling emphasis is
   * closed and an inline caret marks the reveal frontier.
   */
  revealing?: boolean;
}

export function ProseMarkdown({ text, revealing = false }: ProseMarkdownProps) {
  const source = revealing ? prepareRevealSource(text) : text;
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={revealing ? REVEAL_REHYPE_PLUGINS : undefined}
      components={components}
      skipHtml
    >
      {source}
    </ReactMarkdown>
  );
}
