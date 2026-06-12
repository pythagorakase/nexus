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
 *
 * The caret is injected into the parsed tree (after the last text node), not
 * embedded in the markdown source. An earlier sentinel-character approach
 * (U+E000 appended to the source) broke CommonMark's right-flanking rule for
 * any emphasis span ending in punctuation - micromark classifies a private-use
 * char as a word character, so the frame that typed the closing `*` of
 * `*Brena.*` rendered literal asterisks instead of an <em>.
 */
import ReactMarkdown, { type Options } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Element, Root } from "hast";

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
  // Never emit a real <img> (no outbound requests from narrative or
  // freeform player text); render the alt text inert, like links.
  img: ({ alt }) => (alt ? <span className="md-link">{alt}</span> : null),
};

/**
 * Close dangling emphasis markers in a partially revealed markdown string so
 * the typewriter shows `**bo` as bold-in-progress rather than literal stars.
 * Handles both the asterisk and underscore forms found in the corpus
 * (`**`/`*` from Skald, `__`/`_` in the legacy import). Returns the suffix
 * of closing markers to append.
 */
function emphasisClosers(partial: string): string {
  // Markers inside HTML comments (legacy `<!-- SCENE BREAK: S05E06_001 -->`)
  // never reach the renderer - skipHtml drops the whole node, dangling or
  // closed - so they must not count toward delimiter parity. Before this
  // exclusion, the `_` in a scene-break id flipped the underscore count odd
  // and a literal `_` rode the caret for the rest of the reveal.
  const counted = partial.replace(/<!--[\s\S]*?(-->|$)/g, "");
  let closers = "";
  const boldTokens = (counted.match(/\*\*/g) ?? []).length;
  if (boldTokens % 2 === 1) closers += "**";
  const singleStars = (counted.replace(/\*\*/g, "").match(/\*/g) ?? []).length;
  if (singleStars % 2 === 1) closers += "*";
  const doubleUnderscores = (counted.match(/__/g) ?? []).length;
  if (doubleUnderscores % 2 === 1) closers += "__";
  const singleUnderscores = (counted.replace(/__/g, "").match(/_/g) ?? [])
    .length;
  if (singleUnderscores % 2 === 1) closers += "_";
  return closers;
}

/**
 * Build the markdown source for a mid-reveal frame: trim a trailing line
 * that is still just structural markers (`--` typing toward `---` and its
 * longer CommonMark variants, bare `##`, `>`), strip a half-typed trailing
 * emphasis run, and close any dangling emphasis. Stripping the trailing run
 * before computing closers means the frame source never ends in a bare
 * delimiter: a just-typed opener (`the *`) renders as `the ` instead of the
 * empty-emphasis literal `the **`, and a half-typed closer (`**bold*`)
 * rebuilds as `**bold**` instead of leaking stars.
 *
 * The source carries no caret marker - any in-source character would sit
 * between an emphasis delimiter and what follows it and change how
 * CommonMark's flanking rules resolve it (the single-asterisk regression:
 * `*Brena.*` plus a trailing sentinel parsed as literal text because the
 * private-use char counts as a word character, un-right-flanking the
 * closer). The caret is injected into the parsed tree instead (rehypeCaret).
 */
export function prepareRevealSource(partial: string): string {
  const trimmed = partial
    .replace(/(^|\n)[-*_#>]{1,6}[ \t]*$/, "$1")
    .replace(/[*_]+$/, "");
  const closers = emphasisClosers(trimmed);
  if (!closers) return trimmed;
  // A closer preceded by whitespace is not right-flanking and cannot close
  // (`*Before ` + `*` would leak literal stars); attach it to the last
  // non-whitespace character instead.
  return trimmed.replace(/\s+$/, "") + closers;
}

function makeCaret(): Element {
  return {
    type: "element",
    tagName: "span",
    properties: { className: ["type-caret"], ariaHidden: "true" },
    children: [],
  };
}

/**
 * Locate the last non-whitespace text node in tree order. The reveal
 * frontier always sits at the end of the rendered prose (narrative reveals
 * linearly), so the caret belongs immediately after this node - including
 * inside an in-progress emphasis whose closer was auto-appended.
 */
function lastTextPosition(
  parent: Root | Element,
): { parent: Root | Element; index: number } | null {
  for (let i = parent.children.length - 1; i >= 0; i -= 1) {
    const child = parent.children[i];
    if (child.type === "element") {
      const found = lastTextPosition(child);
      if (found) return found;
    } else if (child.type === "text" && child.value.trim() !== "") {
      return { parent, index: i };
    }
  }
  return null;
}

/** Append the inline caret element at the reveal frontier. */
function rehypeCaret() {
  return (tree: Root) => {
    const position = lastTextPosition(tree);
    if (position) {
      position.parent.children.splice(position.index + 1, 0, makeCaret());
    } else {
      // Nothing revealed yet (or only structure): caret stands alone.
      tree.children.push(makeCaret());
    }
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
