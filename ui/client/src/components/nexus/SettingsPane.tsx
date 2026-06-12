/**
 * SettingsPane - the operator's calibration console (NEXUS IRIS, U5).
 *
 * Seven sections: Theme, Typography, Narrative Mode, Model, LORE Budget,
 * Typewriter, App Icon. Every dial writes back to PATCH /api/settings
 * (FastAPI -> nexus.config.loader.save_settings -> nexus.toml) with
 * optimistic cache updates and server confirmation - no local draft state.
 * Theme and font writes flow through ThemeContext/FontContext, which share
 * the same settings query + mutation.
 *
 * Read-only by design (would break a running story or is derived):
 * - the active retrieval embedder (memnon.models.*)
 * - the test database suffix (global.narrative.test_database_suffix)
 * - apex.provider (derived from the @provider.role reference)
 */
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Circle,
  CircleDot,
  RefreshCw,
  Save,
} from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { useFonts } from "@/contexts/FontContext";
import { useSettingsMutation, useSettingsQuery } from "@/hooks/useSettings";
import { themeIconPath } from "@/lib/themeIcons";
import { FONT_CATALOG } from "./fontCatalog";
import type {
  FontSlotId,
  ModelRoleOption,
  SettingsPayload,
  ThemeId,
} from "@/types/settings";

// ──────────────────────────────────────────────────────────────────────────
// Design copy (presentation only - all values come from the settings API)
// ──────────────────────────────────────────────────────────────────────────

const SECTION_INDEX = [
  { id: "theme", label: "Theme" },
  { id: "type", label: "Typography" },
  { id: "narrative", label: "Narrative Mode" },
  { id: "model", label: "Model" },
  { id: "lore", label: "LORE Budget" },
  { id: "reveal", label: "Typewriter" },
  { id: "pwa", label: "App Icon" },
] as const;

type SectionId = (typeof SECTION_INDEX)[number]["id"];

const THEME_PALETTES: Record<
  ThemeId,
  { eyebrow: string; motto: string; swatches: string[]; wordmarkFont: string }
> = {
  veil: {
    eyebrow: "ART NOUVEAU",
    motto: "Magenta rain on blue-black",
    swatches: ["#09101c", "#b83d7a", "#e86a4a", "#e1cd97"],
    wordmarkFont: "Megrim, serif",
  },
  gilded: {
    eyebrow: "ART DECO",
    motto: "Brass engraved on midnight",
    swatches: ["#0a0a0a", "#c9a227", "#7b5524", "#ece2c1"],
    wordmarkFont: "Monoton, fantasy",
  },
  vector: {
    eyebrow: "PHOSPHOR CRT",
    motto: "Scanline void · on the wire",
    swatches: ["#031414", "#00e5ff", "#3aa1ff", "#a3f0ff"],
    wordmarkFont: "Sixtyfour, monospace",
  },
};

const THEME_IDS: ThemeId[] = ["veil", "gilded", "vector"];

const TYPE_SAMPLES: Record<FontSlotId, string> = {
  body: "The night air shimmered with possibility as the lanterns cast warm halos through the mist-laden gardens — and you stepped out into the wet, counting windows.",
  menu: "STATUS: READY  //  CHAPTER: S01·E01·S002  //  SKALD: GENERATING",
  display: "NEXUS",
};

/** Ladder copy applied to ui.lore_budget_slider.stops by index. */
const LADDER_COPY = [
  { label: "COMPACT", note: "fast · tighter context" },
  { label: "BALANCED", note: "default · recommended" },
  { label: "EXPANDED", note: "long-arc · slower" },
  { label: "MAX", note: "ceiling · use sparingly" },
];

// ──────────────────────────────────────────────────────────────────────────
// Card chrome
// ──────────────────────────────────────────────────────────────────────────

function SettingsCard({
  id,
  eyebrow,
  title,
  sub,
  children,
  footer,
}: {
  id: SectionId;
  eyebrow: string;
  title: string;
  sub?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <section className="set-card" id={`set-${id}`}>
      <div className="set-card-frame">
        <header className="set-card-head">
          <div className="set-card-eyebrow brass-glow">[ {eyebrow} ]</div>
          <h3 className="set-card-title">{title}</h3>
          {sub && <p className="set-card-sub">{sub}</p>}
        </header>
        <hr className="set-card-rule" />
        <div className="set-card-body">{children}</div>
        {footer && <footer className="set-card-foot">{footer}</footer>}
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 1. Theme
// ──────────────────────────────────────────────────────────────────────────

function ThemeSection({ active, onPick }: { active: ThemeId; onPick: (t: ThemeId) => void }) {
  return (
    <SettingsCard
      id="theme"
      eyebrow="THEME · STAGE DRESSING"
      title="Three Theatres, One Stage"
      sub="Switching the theme rewrites every chrome surface in the operator's view and persists across sessions. Story content is untouched."
    >
      <div className="theme-grid">
        {THEME_IDS.map((id) => {
          const palette = THEME_PALETTES[id];
          const on = active === id;
          return (
            <button
              key={id}
              className={`theme-card theme-card-${id} ${on ? "on" : ""}`}
              onClick={() => onPick(id)}
              aria-pressed={on}
              data-testid={`theme-${id}`}
            >
              <div
                className="theme-card-wordmark"
                style={{ fontFamily: palette.wordmarkFont }}
              >
                NEXUS
              </div>
              <div className="theme-card-meta">
                <span className="theme-card-name">{id}</span>
                <span className="theme-card-eye">· {palette.eyebrow}</span>
              </div>
              <p className="theme-card-motto">{palette.motto}</p>
              <div className="theme-card-swatches">
                {palette.swatches.map((color) => (
                  <span
                    key={color}
                    className="theme-swatch"
                    style={{ background: color }}
                    title={color}
                  />
                ))}
              </div>
              {on && (
                <span className="theme-card-active">
                  <Check size={11} /> ACTIVE
                </span>
              )}
            </button>
          );
        })}
      </div>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 2. Typography
// ──────────────────────────────────────────────────────────────────────────

function FontSlot({
  slotKey,
  label,
  hint,
  theme,
  value,
  onPick,
  sampleStyle,
}: {
  slotKey: FontSlotId;
  label: string;
  hint: string;
  theme: ThemeId;
  value: string;
  onPick: (font: string) => void;
  sampleStyle?: React.CSSProperties;
}) {
  const options = FONT_CATALOG[theme][slotKey];
  return (
    <div className="font-slot">
      <div className="font-slot-head">
        <span className="font-slot-label">[ {label} ]</span>
        <span className="font-slot-hint">{hint}</span>
      </div>
      <div
        className="font-slot-preview"
        style={{ fontFamily: `"${value}", serif`, ...sampleStyle }}
      >
        {TYPE_SAMPLES[slotKey]}
      </div>
      <div className="font-slot-chips">
        {options.map((opt) => (
          <button
            key={opt.id}
            className={`font-chip ${opt.id === value ? "on" : ""} ${opt.locked ? "locked" : ""}`}
            onClick={() => onPick(opt.id)}
            disabled={Boolean(opt.locked) && opt.id !== value}
          >
            <span
              className="font-chip-name"
              style={{ fontFamily: `"${opt.id}", serif` }}
            >
              {opt.label}
            </span>
            <span className="font-chip-note">{opt.note}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TypographySection() {
  const { theme } = useTheme();
  const { fonts, setFont, resetToKeepers } = useFonts();
  const themeId = theme as ThemeId;
  const slots = fonts[themeId];

  return (
    <SettingsCard
      id="type"
      eyebrow="TYPOGRAPHY · TYPE CARRIAGES"
      title="Font Matrix — Keepers per Slot"
      sub={`Active theme is ${themeId.toUpperCase()}. Choices persist per theme. The marquee font is reserved for the NEXUS wordmark — it appears on theme cards but cannot be substituted within chrome.`}
      footer={
        <>
          <span className="caption dim">
            Slots bind to CSS custom properties — narrative prose, chrome
            labels, and the marquee wordmark.
          </span>
          <button className="btn-soft" onClick={resetToKeepers}>
            <RefreshCw size={12} /> RESET TO KEEPERS
          </button>
        </>
      }
    >
      <FontSlot
        slotKey="body"
        label="BODY · NARRATIVE PROSE"
        hint="--font-narrative · 15–18px · line 1.78"
        theme={themeId}
        value={slots.body}
        onPick={(font) => setFont(themeId, "body", font)}
      />
      <FontSlot
        slotKey="menu"
        label="MENU · CHROME LABELS"
        hint="--font-mono · 10–28px · tracking 0.18em · uppercase"
        theme={themeId}
        value={slots.menu}
        onPick={(font) => setFont(themeId, "menu", font)}
        sampleStyle={{ letterSpacing: "0.18em", textTransform: "uppercase" }}
      />
      <FontSlot
        slotKey="display"
        label="DISPLAY · MARQUEE (LOCKED SLOT)"
        hint="--font-display · NEXUS wordmark only"
        theme={themeId}
        value={slots.display}
        onPick={(font) => setFont(themeId, "display", font)}
        sampleStyle={{
          fontSize: "44px",
          letterSpacing: "0.18em",
          textAlign: "center",
        }}
      />
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 3. Narrative Mode
// ──────────────────────────────────────────────────────────────────────────

function NarrativeSection({
  on,
  suffix,
  onToggle,
}: {
  on: boolean;
  suffix: string;
  onToggle: (value: boolean) => void;
}) {
  return (
    <SettingsCard
      id="narrative"
      eyebrow="NARRATIVE MODE · WRITE ROUTING"
      title="Test Routing for Provisional Turns"
      sub={
        <>
          When the test lever is thrown, new turns are committed to tables
          suffixed <code className="code-inline">{suffix}</code> so production
          stays untouched. The suffix itself is fixed — renaming it mid-story
          would orphan existing test tables.
        </>
      }
    >
      <div className="lever-row">
        <div className="lever-readout">
          <div className="lever-status">
            <span className={`lever-pip ${on ? "on" : ""}`} />
            <span className={`lever-state ${on ? "danger" : ""}`}>
              {on ? "TEST MODE · ENGAGED" : "NOMINAL · LIVE WRITE"}
            </span>
          </div>
          <div className="lever-detail caption dim">
            {on ? (
              <>
                Routing to{" "}
                <code className="code-inline danger">narrative{suffix}</code>,{" "}
                <code className="code-inline danger">chunks{suffix}</code>,{" "}
                <code className="code-inline danger">choices{suffix}</code>
              </>
            ) : (
              <>
                Routing to <code className="code-inline">narrative</code>,{" "}
                <code className="code-inline">chunks</code>,{" "}
                <code className="code-inline">choices</code>
              </>
            )}
          </div>
        </div>
        <button
          className={`lever ${on ? "on" : ""}`}
          onClick={() => onToggle(!on)}
          role="switch"
          aria-checked={on}
          data-testid="lever-test-mode"
        >
          <span className="lever-knob" />
          <span className="lever-tick l">OFF</span>
          <span className="lever-tick r">TEST</span>
        </button>
      </div>
      {on && (
        <div className="alert danger">
          <AlertTriangle size={14} />
          <div>
            <div className="alert-title">TEST MODE ON</div>
            <div className="alert-body">
              New narrative turns will divert to the isolated test tables until
              you flip the lever back. Generation otherwise proceeds normally.
            </div>
          </div>
        </div>
      )}
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 4. Model (role-level bindings only - never raw model IDs)
// ──────────────────────────────────────────────────────────────────────────

function RoleBinding({
  caption,
  currentRef,
  roles,
  onPick,
}: {
  caption: string;
  currentRef: string;
  roles: ModelRoleOption[];
  onPick: (ref: string) => void;
}) {
  const active = roles.find((r) => r.ref === currentRef);
  const providers = Array.from(new Set(roles.map((r) => r.provider)));
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(active ? [active.provider] : []),
  );
  const toggle = (provider: string) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(provider)) {
        next.delete(provider);
      } else {
        next.add(provider);
      }
      return next;
    });
  };

  return (
    <div className="model-binding">
      <div className="model-active">
        <div className="model-active-mark">
          {(active?.provider ?? currentRef.replace(/^@/, ""))[0]?.toUpperCase() ?? "?"}
        </div>
        <div className="model-active-body">
          <span className="caption">{caption}</span>
          <div className="model-active-name">{currentRef}</div>
          <div className="model-active-meta">
            {active ? (
              <>
                <span className="chip-meta">{active.label}</span>
                <span className="chip-meta">{active.provider.toUpperCase()}</span>
                <span className="chip-meta accent">{active.role.toUpperCase()}</span>
              </>
            ) : (
              <span className="chip-meta accent">LITERAL ID · EDIT NEXUS.TOML TO REBIND</span>
            )}
          </div>
        </div>
        <Check size={16} className="model-active-check" />
      </div>

      <ul className="model-providers">
        {providers.map((provider) => {
          const providerRoles = roles.filter((r) => r.provider === provider);
          const isOpen = open.has(provider);
          return (
            <li key={provider} className={`model-provider ${isOpen ? "open" : ""}`}>
              <button className="model-provider-head" onClick={() => toggle(provider)}>
                <ChevronRight size={11} className="model-caret" />
                <span className="model-provider-name">{provider}</span>
                <span className="model-provider-count">{providerRoles.length}</span>
              </button>
              {isOpen && (
                <ul className="model-list">
                  {providerRoles.map((role) => {
                    const on = role.ref === currentRef;
                    return (
                      <li
                        key={role.ref}
                        className={`model-row ${on ? "on" : ""}`}
                        onClick={() => onPick(role.ref)}
                      >
                        <span className="model-radio">
                          {on ? <CircleDot size={12} /> : <Circle size={12} />}
                        </span>
                        <span className="model-name">{role.ref}</span>
                        <span className="model-ctx">{role.label}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ModelSection({
  settings,
  onPickApex,
  onPickWizard,
}: {
  settings: SettingsPayload;
  onPickApex: (ref: string) => void;
  onPickWizard: (ref: string) => void;
}) {
  const meta = settings.settings_meta;
  const roles = meta?.model_roles ?? [];
  const apexAllowed = new Set(meta?.apex_allowed_providers ?? []);
  const apexRoles = roles.filter((r) => apexAllowed.has(r.provider));

  const embedders = Object.entries(settings.memnon?.models ?? {}).filter(
    ([, cfg]) => cfg.is_active,
  );

  return (
    <SettingsCard
      id="model"
      eyebrow="MODEL · ROLE BINDINGS"
      title="LORE / LOGON Binding"
      sub="Bindings are role references resolved through the api_models registry in nexus.toml — edit a role there and every consumer migrates at once. Raw model IDs are never entered here."
    >
      <RoleBinding
        caption="NARRATIVE TURNS · APEX"
        currentRef={settings.apex?.model ?? "—"}
        roles={apexRoles}
        onPick={onPickApex}
      />
      <RoleBinding
        caption="NEW STORY WIZARD"
        currentRef={settings.wizard?.default_model ?? "—"}
        roles={roles}
        onPick={onPickWizard}
      />

      <div className="model-locked">
        <div className="model-locked-head">
          <span className="font-slot-label">[ RETRIEVAL EMBEDDER · LOCKED ]</span>
        </div>
        {embedders.map(([name, cfg]) => (
          <div key={name} className="model-locked-row">
            <span className="model-locked-name">{name}</span>
            <span className="chip-meta">{cfg.dimensions} DIM</span>
            <span className="chip-meta accent">ACTIVE</span>
          </div>
        ))}
        <p className="model-locked-copy">
          Every stored memory is encoded with this model. Switching it
          mid-story orphans the archive — change requires a re-embedding
          campaign, not a settings toggle.
        </p>
      </div>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 5. LORE Budget
// ──────────────────────────────────────────────────────────────────────────

function LoreSection({
  settings,
  onCommit,
}: {
  settings: SettingsPayload;
  onCommit: (value: number) => void;
}) {
  const slider = settings.ui?.lore_budget_slider;
  const saved = settings.lore?.token_budget?.apex_context_window ?? 0;
  const reserve = settings.lore?.token_budget?.system_prompt_tokens;
  const [draft, setDraft] = useState<number | null>(null);
  const value = draft ?? saved;
  const dirty = draft !== null && draft !== saved;

  // When the server value moves under the draft (optimistic commit applied,
  // or a failed PATCH rolled the cache back), the draft is stale - drop it
  // so the control always re-syncs to server truth.
  useEffect(() => {
    setDraft(null);
  }, [saved]);

  if (!slider) return null;

  const stopTolerance = slider.step * 5;
  const ladderLabel =
    LADDER_COPY[slider.stops.findIndex((s) => Math.abs(s - value) < stopTolerance)]
      ?.label ?? "CUSTOM";

  return (
    <SettingsCard
      id="lore"
      eyebrow="LORE · TOKEN BUDGETS"
      title="Apex Context Window"
      sub="The maximum token allotment for context assembly before each LORE / LOGON call. Smaller is faster; larger lets the agent reach further back."
      footer={
        <>
          <span className={`caption ${dirty ? "warning" : "dim"}`}>
            {dirty ? "● UNSAVED · " : ""}
            saved: {saved.toLocaleString()} tok
            {reserve !== undefined &&
              ` · system prompt reserve: ${reserve.toLocaleString()} tok`}
          </span>
          <button
            className="btn-primary"
            disabled={!dirty}
            onClick={() => {
              onCommit(value);
              setDraft(null);
            }}
            data-testid="lore-commit"
          >
            <Save size={12} /> COMMIT
          </button>
        </>
      }
    >
      <div className="lore-readout">
        <div className="lore-value">
          {value.toLocaleString()}
          <span className="lore-unit">tok</span>
        </div>
        <div className="lore-label">{ladderLabel}</div>
      </div>
      <div className="lore-stops">
        {slider.stops.map((stop, i) => {
          const isSel = Math.abs(stop - value) < stopTolerance;
          const copy = LADDER_COPY[i] ?? { label: `${stop / 1000}K`, note: "" };
          return (
            <button
              key={stop}
              className={`lore-stop ${isSel ? "on" : ""}`}
              onClick={() => setDraft(stop)}
            >
              <span
                className="lore-stop-bar"
                style={{ height: `${(stop / slider.max) * 60 + 12}px` }}
              />
              <span className="lore-stop-num">{stop / 1000}K</span>
              <span className="lore-stop-label">{copy.label}</span>
              <span className="lore-stop-note caption dim">{copy.note}</span>
            </button>
          );
        })}
      </div>
      <div className="lore-slider-row">
        <input
          type="range"
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={value}
          onChange={(e) => setDraft(parseInt(e.target.value, 10))}
          className="lore-slider"
        />
        <div className="lore-slider-axis">
          <span>{slider.min / 1000}K</span>
          <span>{slider.max / 2000}K</span>
          <span>{slider.max / 1000}K</span>
        </div>
      </div>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 6. Typewriter
// ──────────────────────────────────────────────────────────────────────────

function TypewriterSection({
  settings,
  onCommit,
}: {
  settings: SettingsPayload;
  onCommit: (value: number) => void;
}) {
  const saved = settings.ui?.typewriter_ms_per_char ?? 0;
  const bounds = settings.settings_meta?.typewriter;
  const [draft, setDraft] = useState<number | null>(null);
  const value = draft ?? saved;
  const dirty = draft !== null && draft !== saved;

  // Same staleness rule as LoreSection: server movement invalidates the draft.
  useEffect(() => {
    setDraft(null);
  }, [saved]);

  if (!bounds) return null;

  return (
    <SettingsCard
      id="reveal"
      eyebrow="REVEAL · TYPE SPEED"
      title="Typewriter Cadence"
      sub="Milliseconds per character for incoming narrative chunks. The design system recommends 30–50 ms/char; the next generated chunk picks the change up immediately."
      footer={
        <>
          <span className={`caption ${dirty ? "warning" : "dim"}`}>
            {dirty ? "● UNSAVED · " : ""}
            saved: {saved} ms/char
          </span>
          <button
            className="btn-primary"
            disabled={!dirty}
            onClick={() => {
              onCommit(value);
              setDraft(null);
            }}
            data-testid="typewriter-commit"
          >
            <Save size={12} /> COMMIT
          </button>
        </>
      }
    >
      <div className="lore-readout">
        <div className="lore-value">
          {value}
          <span className="lore-unit">ms/char</span>
        </div>
        <div className="lore-label">
          {value >= 30 && value <= 50 ? "DESIGN RANGE" : "CUSTOM"}
        </div>
      </div>
      <div className="lore-slider-row">
        <input
          type="range"
          min={bounds.min}
          max={bounds.max}
          step={1}
          value={value}
          onChange={(e) => setDraft(parseInt(e.target.value, 10))}
          className="lore-slider"
          data-testid="typewriter-slider"
        />
        <div className="lore-slider-axis">
          <span>{bounds.min}</span>
          <span>{Math.round((bounds.min + bounds.max) / 2)}</span>
          <span>{bounds.max}</span>
        </div>
      </div>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 7. App Icon (Per-Theme, Locked)
// ──────────────────────────────────────────────────────────────────────────

function PwaSection() {
  const { theme } = useTheme();

  return (
    <SettingsCard
      id="pwa"
      eyebrow="PWA · HOME-SCREEN GLYPH"
      title="App Icon"
      sub="One mark, three liveries. The favicon and home-screen glyph follow the active theme; the PWA install icon is baked at build time on the default theme (Veil)."
    >
      <div className="pwa-icon-row">
        {THEME_IDS.map((id) => (
          <div
            key={id}
            className={`pwa-icon-tile ${theme === id ? "on" : ""}`}
            data-testid={`pwa-icon-${id}`}
          >
            <img src={themeIconPath(id, 192)} alt={`${id} app icon`} />
          </div>
        ))}
      </div>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Anchor rail + composed pane
// ──────────────────────────────────────────────────────────────────────────

function SectionRail({
  active,
  onPick,
}: {
  active: SectionId;
  onPick: (id: SectionId) => void;
}) {
  return (
    <aside className="set-rail">
      <div className="eyebrow brass-glow">CALIBRATION</div>
      <ul>
        {SECTION_INDEX.map((s) => (
          <li key={s.id}>
            <button
              className={`set-rail-btn ${active === s.id ? "on" : ""}`}
              onClick={() => onPick(s.id)}
            >
              <span className="set-rail-label">{s.label}</span>
              {active === s.id && <span className="set-rail-bar" />}
            </button>
          </li>
        ))}
      </ul>
      <div className="set-rail-foot">
        <span className="caption dim">/ AGENT SETTINGS</span>
        <span className="caption dim">NEXUS.TOML · LIVE</span>
      </div>
    </aside>
  );
}

export function SettingsPane() {
  const { data: settings, error } = useSettingsQuery();

  if (error) {
    return (
      <div className="pane-notice" data-testid="settings-pane">
        <span className="notice-text">[ SETTINGS UNAVAILABLE ]</span>
        <span className="notice-detail">{error.message}</span>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="pane-notice" data-testid="settings-pane">
        <span className="notice-text">[ RECEIVING ]</span>
      </div>
    );
  }

  // The console only mounts once settings exist, so its scroll-tracking
  // effect can bind on mount with the scroller guaranteed present.
  return <SettingsConsole settings={settings} />;
}

function SettingsConsole({ settings }: { settings: SettingsPayload }) {
  const { theme, setTheme } = useTheme();
  const mutation = useSettingsMutation();

  const [active, setActive] = useState<SectionId>("theme");
  const scrollerRef = useRef<HTMLDivElement>(null);

  const jumpTo = (id: SectionId) => {
    setActive(id);
    const root = scrollerRef.current;
    const el = root?.querySelector<HTMLElement>(`#set-${id}`);
    if (el && root) root.scrollTo({ top: el.offsetTop - 12, behavior: "smooth" });
  };

  // Track which section is in view as the operator scrolls.
  useEffect(() => {
    const root = scrollerRef.current;
    if (!root) return;
    const onScroll = () => {
      const top = root.scrollTop + 80;
      let current: SectionId = "theme";
      for (const s of SECTION_INDEX) {
        const el = root.querySelector<HTMLElement>(`#set-${s.id}`);
        if (el && el.offsetTop <= top) current = s.id;
      }
      setActive(current);
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, []);

  const testMode = settings.global?.narrative?.test_mode ?? false;
  const testSuffix = settings.global?.narrative?.test_database_suffix ?? "_test";

  return (
    <div className="settings-pane-v2" data-testid="settings-pane">
      <SectionRail active={active} onPick={jumpTo} />
      <div className="set-scroller" ref={scrollerRef}>
        <header className="set-header">
          <div className="eyebrow brass-glow">[ AGENT CALIBRATION ]</div>
          <h2 className="set-headline">Configuration</h2>
          <p className="set-headline-sub">
            Every dial on this console writes back to{" "}
            <code className="code-inline">nexus.toml</code> through the
            settings API. The agent picks up changes on the next narrative
            turn — no restart, no incantations.
          </p>
          {mutation.isError && (
            <div className="alert danger">
              <AlertTriangle size={14} />
              <div>
                <div className="alert-title">WRITE REJECTED</div>
                <div className="alert-body">{mutation.error.message}</div>
              </div>
            </div>
          )}
        </header>

        <ThemeSection active={theme as ThemeId} onPick={(t) => setTheme(t)} />
        <TypographySection />
        <NarrativeSection
          on={testMode}
          suffix={testSuffix}
          onToggle={(value) => mutation.mutate({ test_mode: value })}
        />
        <ModelSection
          settings={settings}
          onPickApex={(ref) => mutation.mutate({ apex_model_ref: ref })}
          onPickWizard={(ref) => mutation.mutate({ wizard_model_ref: ref })}
        />
        <LoreSection
          settings={settings}
          onCommit={(value) => mutation.mutate({ apex_context_window: value })}
        />
        <TypewriterSection
          settings={settings}
          onCommit={(value) => mutation.mutate({ typewriter_ms_per_char: value })}
        />
        <PwaSection />

        <div className="set-foot">
          <div className="set-foot-rule" />
          <div className="caption dim">END OF CONSOLE</div>
        </div>
      </div>
    </div>
  );
}
