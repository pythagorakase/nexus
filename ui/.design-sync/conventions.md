# Building with NEXUS Iris

NEXUS Iris is the UI of an interactive-fiction story engine: an Art Nouveau /
Art Deco dark aesthetic, served from React + Tailwind with CSS-variable design
tokens. Components are real, compiled, and importable from `nexus-ui`
(`window.NexusIris.*`).

## Always wrap the tree in `DesignThemeRoot`

```jsx
import { DesignThemeRoot, Card, CardHeader, CardTitle, CardContent, Button } from 'nexus-ui';

<DesignThemeRoot>
  <Card className="max-w-sm">
    <CardHeader><CardTitle>Save Slot 02</CardTitle></CardHeader>
    <CardContent className="text-muted-foreground">Chapter Seven — The Veil</CardContent>
    <div className="flex gap-2 p-6 pt-0">
      <Button>Continue</Button>
      <Button variant="outline">Load</Button>
    </div>
  </Card>
</DesignThemeRoot>
```

`DesignThemeRoot` applies the default **Veil** theme (the `.dark` class), loads
the brand fonts, and provides the Theme / Font / Query context the components
read. **Without it**: components that call theme/settings hooks throw, and the
design tokens + fonts are absent (everything renders unstyled in a browser
default font). Wrap once, at the root.

## Themes

Veil is the default (Art Nouveau, magenta + coral on deep blue-black). Two
override themes exist via a class on the root: `theme-gilded` (Art Deco, brass
on ink black) and `theme-vector` (terminal/cyberpunk). The `deco/*` components
are designed for Gilded; the `veil/*` frames for Veil.

## Styling idiom: Tailwind utilities over semantic token classes

Style with Tailwind utilities backed by the design tokens — **never invent
hex/raw colors**; every color is a token so it tracks the active theme. Use
these families (each is `bg-`, `text-`, and/or `border-`):

`background`, `foreground`, `card` / `card-foreground`, `popover` /
`popover-foreground`, `primary` / `primary-foreground`, `secondary` /
`secondary-foreground`, `muted` / `muted-foreground`, `accent` /
`accent-foreground`, `destructive` / `destructive-foreground`, `border`,
`input`, `ring`, `sidebar` (+ `-foreground`/`-border`/`-primary`/`-accent`),
`chart-1`…`chart-5`.

Examples: `bg-background text-foreground`, `bg-card border border-card-border`,
`bg-primary text-primary-foreground`, `text-muted-foreground`,
`bg-destructive`. Radii: `rounded-sm` / `rounded-md` / `rounded-lg`.

Fonts are token-driven utilities — `font-sans` (body), `font-serif`,
`font-mono` (chrome), `font-display` (marquee). They resolve to the active
theme's keeper faces (Veil: Spectral / Cinzel / Megrim). For raw values in
custom layout glue, reference tokens directly: `hsl(var(--primary))`,
`hsl(var(--background))`, `var(--font-display)`.

## Where the truth lives

- `styles.css` — the token + font + component-style closure every design
  receives. Read it before styling.
- `components/<group>/<Name>/<Name>.prompt.md` — per-component usage notes.
- `components/<group>/<Name>/<Name>.d.ts` — the prop contract (`<Name>Props`).

Compound components (Card, Dialog, Accordion, Table, Select, Sidebar, …)
export their sub-parts from `nexus-ui` — import and compose them together.
