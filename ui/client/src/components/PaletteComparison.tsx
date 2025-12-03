/**
 * Palette Comparison Modal
 * Shows side-by-side comparison of all three theme palettes with font information.
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface PaletteComparisonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ColorDef {
  hsl: string;
  hex: string;
  name: string;
}

interface ThemeDef {
  name: string;
  subtitle: string;
  hueRange: string;
  colors: Record<string, ColorDef>;
  fonts: {
    body: string;
    mono: string;
    monoStyle?: string;
    display: string;
    displayStyle?: string;
  };
}

const gilded: ThemeDef = {
  name: "Gilded",
  subtitle: "Art Deco • Warm",
  hueRange: "30-50",
  colors: {
    background: { hsl: "0 0% 4%", hex: "#0a0a0a", name: "Ink Black" },
    foreground: { hsl: "45 20% 93%", hex: "#f5f0e1", name: "Cream" },
    primary: { hsl: "43 74% 47%", hex: "#c9a227", name: "Warm Brass" },
    "primary-fg": { hsl: "0 0% 4%", hex: "#0a0a0a", name: "Ink Black" },
    accent: { hsl: "45 55% 60%", hex: "#d4b85a", name: "Light Gold" },
    "accent-fg": { hsl: "0 0% 4%", hex: "#0a0a0a", name: "Ink Black" },
    muted: { hsl: "30 15% 12%", hex: "#1f1a15", name: "Dark Bronze" },
    "muted-fg": { hsl: "43 40% 52%", hex: "#b59953", name: "Muted Brass" },
    secondary: { hsl: "35 20% 18%", hex: "#2a2520", name: "Warm Gray" },
    "secondary-fg": { hsl: "45 20% 85%", hex: "#e0d9c8", name: "Light Cream" },
    destructive: { hsl: "0 65% 50%", hex: "#d43d3d", name: "Deep Red" },
    border: { hsl: "43 30% 25%", hex: "#524a32", name: "Bronze Border" },
    ring: { hsl: "43 74% 47%", hex: "#c9a227", name: "Brass Ring" },
    chart1: { hsl: "43 74% 47%", hex: "#c9a227", name: "Brass" },
    chart2: { hsl: "30 50% 45%", hex: "#ac7a36", name: "Bronze" },
    chart3: { hsl: "45 60% 65%", hex: "#d4bc6a", name: "Light Gold" },
    chart4: { hsl: "35 40% 35%", hex: "#7d6642", name: "Dark Bronze" },
    chart5: { hsl: "50 30% 50%", hex: "#a6995c", name: "Muted Gold" },
  },
  fonts: {
    body: "Cormorant Garamond",
    mono: "Space Mono",
    display: "Monoton",
  },
};

const vector: ThemeDef = {
  name: "Vector",
  subtitle: "Digital • Cool",
  hueRange: "180-200",
  colors: {
    background: { hsl: "180 30% 3%", hex: "#050a0a", name: "Deep Void" },
    foreground: { hsl: "180 30% 90%", hex: "#dff0f0", name: "Ice White" },
    primary: { hsl: "185 100% 50%", hex: "#00e5ff", name: "Neon Cyan" },
    "primary-fg": { hsl: "180 30% 3%", hex: "#050a0a", name: "Deep Void" },
    accent: { hsl: "190 80% 60%", hex: "#4dd4e8", name: "Electric Blue" },
    "accent-fg": { hsl: "180 30% 3%", hex: "#050a0a", name: "Deep Void" },
    muted: { hsl: "185 20% 12%", hex: "#182224", name: "Dark Slate" },
    "muted-fg": { hsl: "185 40% 55%", hex: "#5aa3ad", name: "Muted Teal" },
    secondary: { hsl: "190 25% 15%", hex: "#1d2a2e", name: "Steel Gray" },
    "secondary-fg": { hsl: "180 25% 80%", hex: "#c0d6d6", name: "Soft Cyan" },
    destructive: { hsl: "350 80% 55%", hex: "#e83a5d", name: "Neon Pink" },
    border: { hsl: "185 50% 20%", hex: "#1a4048", name: "Teal Border" },
    ring: { hsl: "185 100% 50%", hex: "#00e5ff", name: "Cyan Ring" },
    chart1: { hsl: "185 100% 50%", hex: "#00e5ff", name: "Cyan" },
    chart2: { hsl: "200 90% 55%", hex: "#2196f3", name: "Blue" },
    chart3: { hsl: "170 70% 50%", hex: "#26c6a0", name: "Teal" },
    chart4: { hsl: "260 60% 60%", hex: "#8b6dbd", name: "Purple" },
    chart5: { hsl: "320 70% 60%", hex: "#d456a3", name: "Magenta" },
  },
  fonts: {
    body: "Source Code Pro",
    mono: "Source Code Pro",
    display: "Sixtyfour",
  },
};

const veil: ThemeDef = {
  name: "Veil",
  subtitle: "Art Nouveau • Mystical",
  hueRange: "300-340",
  colors: {
    background: { hsl: "230 40% 8%", hex: "#0d1526", name: "Midnight Indigo" },
    foreground: { hsl: "42 50% 78%", hex: "#e8d5a3", name: "Warm Cream" },
    primary: { hsl: "320 55% 50%", hex: "#b83d7a", name: "Magenta Rose" },
    "primary-fg": { hsl: "42 45% 92%", hex: "#f5edd8", name: "Pale Cream" },
    accent: { hsl: "15 75% 60%", hex: "#e86a4a", name: "Coral Fire" },
    "accent-fg": { hsl: "230 40% 8%", hex: "#0d1526", name: "Midnight Indigo" },
    muted: { hsl: "235 25% 14%", hex: "#1a1d2e", name: "Deep Night" },
    "muted-fg": { hsl: "30 35% 55%", hex: "#a68a6a", name: "Dusty Bronze" },
    secondary: { hsl: "260 30% 18%", hex: "#2a2040", name: "Dark Plum" },
    "secondary-fg": { hsl: "40 30% 78%", hex: "#d4c8a8", name: "Soft Cream" },
    destructive: { hsl: "350 70% 55%", hex: "#d94452", name: "Crimson" },
    border: { hsl: "25 50% 35%", hex: "#855530", name: "Copper" },
    ring: { hsl: "320 55% 50%", hex: "#b83d7a", name: "Magenta Ring" },
    chart1: { hsl: "320 55% 50%", hex: "#b83d7a", name: "Magenta Rose" },
    chart2: { hsl: "15 75% 60%", hex: "#e86a4a", name: "Coral" },
    chart3: { hsl: "35 70% 50%", hex: "#d9952a", name: "Amber" },
    chart4: { hsl: "340 50% 45%", hex: "#ad3d5c", name: "Wine" },
    chart5: { hsl: "45 65% 65%", hex: "#dbb854", name: "Gold" },
  },
  fonts: {
    body: "Spectral",
    mono: "Cinzel",
    monoStyle: "small-caps",
    display: "Cinzel",
    displayStyle: "uppercase",
  },
};

const themes = [gilded, vector, veil];

function Swatch({
  color,
  label,
  small = false,
}: {
  color: ColorDef;
  label: string;
  small?: boolean;
}) {
  const isDark = color.hex.includes("0a0a") || color.hex.includes("0d15");
  return (
    <div className={`flex items-center gap-2.5 ${small ? "mb-1.5" : "mb-2.5"}`}>
      <div
        className={`${small ? "w-7 h-7" : "w-10 h-10"} rounded border border-white/10`}
        style={{
          backgroundColor: color.hex,
          boxShadow: isDark ? "inset 0 0 0 1px rgba(255,255,255,0.1)" : "none",
        }}
      />
      <div className="flex-1 min-w-0">
        <div
          className={`${small ? "text-[11px]" : "text-xs"} font-semibold text-foreground/90 capitalize`}
        >
          {label.replace("-", " ")}
        </div>
        <div className="text-[10px] text-muted-foreground font-mono truncate">
          {color.hex} • {color.name}
        </div>
      </div>
    </div>
  );
}

function FontSample({
  fontName,
  style,
  label,
}: {
  fontName: string;
  style?: string;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide w-12">
        {label}
      </div>
      <div
        className="text-sm text-foreground/90 truncate"
        style={{
          fontFamily: fontName,
          fontVariant: style === "small-caps" ? "small-caps" : undefined,
          textTransform: style === "uppercase" ? "uppercase" : undefined,
        }}
      >
        {fontName}
        {style && <span className="text-[10px] text-muted-foreground ml-2">({style})</span>}
      </div>
    </div>
  );
}

function PalettePanel({
  theme,
  position,
}: {
  theme: ThemeDef;
  position: "left" | "center" | "right";
}) {
  const coreColors = [
    "background",
    "foreground",
    "primary",
    "accent",
    "muted-fg",
    "destructive",
  ];
  const semanticColors = ["secondary", "secondary-fg", "border", "ring"];
  const chartColors = ["chart1", "chart2", "chart3", "chart4", "chart5"];

  const borderRadius =
    position === "left"
      ? "rounded-l-lg"
      : position === "right"
        ? "rounded-r-lg"
        : "";

  return (
    <div
      className={`flex-1 p-4 min-w-0 ${borderRadius}`}
      style={{ backgroundColor: theme.colors.background.hex }}
    >
      {/* Core Colors */}
      <div className="mb-4">
        <div
          className="text-[10px] mb-2 uppercase tracking-widest"
          style={{ color: theme.colors["muted-fg"].hex }}
        >
          Core Palette
        </div>
        {coreColors.map((key) => (
          <Swatch key={key} color={theme.colors[key]} label={key} />
        ))}
      </div>

      {/* Semantic Colors */}
      <div className="mb-4">
        <div
          className="text-[10px] mb-2 uppercase tracking-widest"
          style={{ color: theme.colors["muted-fg"].hex }}
        >
          UI Elements
        </div>
        {semanticColors.map((key) => (
          <Swatch key={key} color={theme.colors[key]} label={key} small />
        ))}
      </div>

      {/* Chart Colors */}
      <div className="mb-4">
        <div
          className="text-[10px] mb-2 uppercase tracking-widest"
          style={{ color: theme.colors["muted-fg"].hex }}
        >
          Chart Palette
        </div>
        <div className="flex gap-1.5 mb-2">
          {chartColors.map((key) => (
            <div
              key={key}
              className="flex-1 h-8 rounded"
              style={{
                backgroundColor: theme.colors[key].hex,
                boxShadow: `0 0 8px ${theme.colors[key].hex}40`,
              }}
              title={`${key}: ${theme.colors[key].hex}`}
            />
          ))}
        </div>
      </div>

      {/* Fonts */}
      <div>
        <div
          className="text-[10px] mb-2 uppercase tracking-widest"
          style={{ color: theme.colors["muted-fg"].hex }}
        >
          Typography
        </div>
        <FontSample fontName={theme.fonts.body} label="Body" />
        <FontSample
          fontName={theme.fonts.mono}
          style={theme.fonts.monoStyle}
          label="Mono"
        />
        <FontSample
          fontName={theme.fonts.display}
          style={theme.fonts.displayStyle}
          label="Display"
        />
      </div>
    </div>
  );
}

export function PaletteComparison({ open, onOpenChange }: PaletteComparisonProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] p-0 overflow-hidden">
        {/* Sticky freeze-pane header with theme names in their own display fonts */}
        <DialogHeader className="sr-only">
          <DialogTitle>Theme Palette Comparison</DialogTitle>
          <DialogDescription>Color and typography definitions for each theme</DialogDescription>
        </DialogHeader>

        <div className="sticky top-0 z-10 bg-background border-b border-border">
          <div className="flex">
            {themes.map((theme) => (
              <div
                key={theme.name}
                className="flex-1 py-4 text-center"
                style={{ backgroundColor: theme.colors.background.hex }}
              >
                <span
                  style={{
                    fontFamily: theme.fonts.display,
                    textTransform: theme.fonts.displayStyle === "uppercase" ? "uppercase" : undefined,
                    color: theme.colors.primary.hex,
                    textShadow: `0 0 20px ${theme.colors.primary.hex}40`,
                  }}
                  className="text-xl tracking-wide"
                >
                  {theme.name}
                </span>
                <div
                  className="text-[10px] mt-1"
                  style={{ color: theme.colors["muted-fg"].hex }}
                >
                  {theme.subtitle}
                </div>
              </div>
            ))}
          </div>
        </div>

        <ScrollArea className="max-h-[calc(90vh-80px)]">
          <div className="px-4 pb-4">
            {/* Theme panels */}
            <div className="flex gap-0">
              {themes.map((theme, i) => (
                <PalettePanel
                  key={theme.name}
                  theme={theme}
                  position={i === 0 ? "left" : i === 2 ? "right" : "center"}
                />
              ))}
            </div>

            {/* Key differentiators */}
            <div className="mt-4 p-4 rounded-lg bg-background/50 border border-border">
              <div className="font-semibold text-sm mb-2 text-foreground">
                Key Differentiators
              </div>
              <div className="grid grid-cols-3 gap-3 text-[11px] text-muted-foreground">
                <div>
                  <span style={{ color: gilded.colors.primary.hex }}>●</span>{" "}
                  Gilded: Warm (30-50), brass/bronze, vintage luxury
                </div>
                <div>
                  <span style={{ color: vector.colors.primary.hex }}>●</span>{" "}
                  Vector: Cool (180-200), cyan/teal, digital synthetic
                </div>
                <div>
                  <span style={{ color: veil.colors.primary.hex }}>●</span>{" "}
                  Veil: Red-violet (300-340), magenta/coral, mystical twilight
                </div>
              </div>
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
