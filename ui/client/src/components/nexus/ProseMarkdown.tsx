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
 */
import ReactMarkdown, { type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

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

const REMARK_PLUGINS = [remarkGfm];

/* Inline-only rendering for single-line labels (choice buttons). Emphasis
   and strong render as real <em>/<strong>; every other construct is
   unwrapped to its text (unwrapDisallowed), so a stray heading marker or
   link in a choice can never produce block layout inside a button. */
const INLINE_ALLOWED_ELEMENTS = ["p", "em", "strong"];
const INLINE_COMPONENTS: Options["components"] = {
  // The paragraph wrapper would be block-level inside the button; choices
  // are single-line labels, so unwrap it.
  p: ({ children }) => <>{children}</>,
};

/**
 * InlineMarkdown - emphasis/strong only, no block elements. For choice
 * button labels, which the storyteller marks up with the same `*italic*` /
 * `**bold**` dialect as prose (PR #386 dialect survey) but which previously
 * rendered the markers as literal asterisks.
 */
export function InlineMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      components={INLINE_COMPONENTS}
      allowedElements={INLINE_ALLOWED_ELEMENTS}
      unwrapDisallowed
      skipHtml
    >
      {text}
    </ReactMarkdown>
  );
}

interface ProseMarkdownProps {
  text: string;
}

export function ProseMarkdown({ text }: ProseMarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      components={components}
      skipHtml
    >
      {text}
    </ReactMarkdown>
  );
}
