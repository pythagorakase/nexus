/**
 * SettingsPane - the operator's settings console (NEXUS IRIS, U5).
 *
 * Seven sections: Theme, Typography, Test Mode, Model, Context Length,
 * Typewriter, App Icon. Every dial writes back to PATCH /api/settings
 * (FastAPI -> nexus.config.loader.save_settings -> nexus.toml) with
 * optimistic cache updates and server confirmation - no local draft state.
 * Theme and font writes flow through ThemeContext/FontContext, which share
 * the same settings query + mutation.
 *
 * Presentation follows the visual minimalism principle (PR #388): one label
 * per section matching its rail name, no explanatory prose in persistent
 * chrome, no internal module names in UI copy.
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Circle, CircleDot, RefreshCw, Save } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { KEEPERS, useFonts } from "@/contexts/FontContext";
import { useSettingsMutation, useSettingsQuery } from "@/hooks/useSettings";
import { themeIconPath } from "@/lib/themeIcons";
import { FONT_CATALOG } from "./fontCatalog";
import type {
  FontSlotId,
  FontSlots,
  SettingsPayload,
  ThemeId,
} from "@/types/settings";

// ──────────────────────────────────────────────────────────────────────────
// Section index (rail names double as the one label per card)
// ──────────────────────────────────────────────────────────────────────────

const SECTION_INDEX = [
  { id: "theme", label: "Theme" },
  { id: "type", label: "Typography" },
  { id: "narrative", label: "Test Mode" },
  { id: "model", label: "Model" },
  { id: "lore", label: "Context Length" },
  { id: "reveal", label: "Typewriter" },
  { id: "pwa", label: "App Icon" },
] as const;

type SectionId = (typeof SECTION_INDEX)[number]["id"];

const THEME_IDS: ThemeId[] = ["veil", "gilded", "vector"];

const LOREM_SNIPPET =
  "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt.";

const TYPE_SAMPLES: Record<FontSlotId, string> = {
  body: "The night air shimmered with possibility as the lanterns cast warm halos through the mist.",
  menu: "STATUS: READY  //  CHAPTER 01  //  SCENE 02",
  display: "NEXUS",
};

// ──────────────────────────────────────────────────────────────────────────
// Card chrome - one label, body, optional footer
// ──────────────────────────────────────────────────────────────────────────

function SettingsCard({
  id,
  label,
  children,
  footer,
}: {
  id: SectionId;
  label: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <section className="set-card" id={`set-${id}`}>
      <div className="set-card-frame">
        <header className="set-card-head">
          <div className="set-card-eyebrow brass-glow">[ {label} ]</div>
        </header>
        <hr className="set-card-rule" />
        <div className="set-card-body">{children}</div>
        {footer && <footer className="set-card-foot">{footer}</footer>}
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 1. Theme - each card is the theme's own type specimen: name in its
// marquee font, "menu" in its menu font, lorem ipsum in its body font.
// ──────────────────────────────────────────────────────────────────────────

function ThemeSection({ active, onPick }: { active: ThemeId; onPick: (t: ThemeId) => void }) {
  const { fonts } = useFonts();

  return (
    <SettingsCard id="theme" label="THEME">
      <div className="theme-grid">
        {THEME_IDS.map((id) => {
          // GET /api/settings serves raw nexus.toml, so a hand-edited
          // [ui.fonts] could arrive partial; guard with the keeper matrix
          // exactly as FontContext does for the active theme.
          const slots: FontSlots = fonts[id] ?? KEEPERS[id];
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
                style={{ fontFamily: `"${slots.display}"` }}
              >
                {id}
              </div>
              <div
                className="theme-card-menuline"
                style={{ fontFamily: `"${slots.menu}"` }}
              >
                menu
              </div>
              <p
                className="theme-card-lorem"
                style={{ fontFamily: `"${slots.body}"` }}
              >
                {LOREM_SNIPPET}
              </p>
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
  theme,
  value,
  onPick,
  sampleStyle,
}: {
  slotKey: FontSlotId;
  label: string;
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
      label="TYPOGRAPHY"
      footer={
        <button className="btn-soft" onClick={resetToKeepers}>
          <RefreshCw size={12} /> RESET
        </button>
      }
    >
      <FontSlot
        slotKey="body"
        label="BODY"
        theme={themeId}
        value={slots.body}
        onPick={(font) => setFont(themeId, "body", font)}
      />
      <FontSlot
        slotKey="menu"
        label="MENU"
        theme={themeId}
        value={slots.menu}
        onPick={(font) => setFont(themeId, "menu", font)}
        sampleStyle={{ letterSpacing: "0.18em", textTransform: "uppercase" }}
      />
      <FontSlot
        slotKey="display"
        label="MARQUEE"
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
// 3. Test Mode
// ──────────────────────────────────────────────────────────────────────────

function TestModeSection({
  on,
  onToggle,
}: {
  on: boolean;
  onToggle: (value: boolean) => void;
}) {
  return (
    <SettingsCard id="narrative" label="TEST MODE">
      <div className="lever-row">
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
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 4. Model - one picker; selection binds both narrative turns and the
// new-story wizard to the same @provider.role reference in nexus.toml.
// ──────────────────────────────────────────────────────────────────────────

function ModelSection({
  settings,
  onPick,
}: {
  settings: SettingsPayload;
  onPick: (ref: string) => void;
}) {
  const meta = settings.settings_meta;
  const roles = meta?.model_roles ?? [];
  const apexAllowed = new Set(meta?.apex_allowed_providers ?? []);
  const options = roles.filter((r) => apexAllowed.has(r.provider));
  const providers = Array.from(new Set(options.map((r) => r.provider)));
  const current = settings.apex?.model ?? "";

  return (
    <SettingsCard id="model" label="MODEL">
      <ul className="model-providers">
        {providers.map((provider) => (
          <li key={provider} className="model-provider open">
            <div className="model-provider-head">
              <span className="model-provider-name">{provider}</span>
            </div>
            <ul className="model-list">
              {options
                .filter((r) => r.provider === provider)
                .map((role) => {
                  const on = role.ref === current;
                  return (
                    <li
                      key={role.ref}
                      className={`model-row ${on ? "on" : ""}`}
                      onClick={() => onPick(role.ref)}
                      data-testid={`model-${role.provider}-${role.role}`}
                    >
                      <span className="model-radio">
                        {on ? <CircleDot size={12} /> : <Circle size={12} />}
                      </span>
                      <span className="model-name">{role.label}</span>
                    </li>
                  );
                })}
            </ul>
          </li>
        ))}
      </ul>
    </SettingsCard>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 5. Context Length
// ──────────────────────────────────────────────────────────────────────────

function ContextLengthSection({
  settings,
  onCommit,
}: {
  settings: SettingsPayload;
  onCommit: (value: number) => void;
}) {
  const slider = settings.ui?.lore_budget_slider;
  const saved = settings.lore?.token_budget?.apex_context_window ?? 0;
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

  return (
    <SettingsCard
      id="lore"
      label="CONTEXT LENGTH"
      footer={
        <>
          <span className={`caption ${dirty ? "warning" : "dim"}`}>
            {dirty ? "● UNSAVED" : ""}
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
      </div>
      <div className="lore-stops">
        {slider.stops.map((stop) => {
          const isSel = Math.abs(stop - value) < stopTolerance;
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

  // Same staleness rule as ContextLengthSection: server movement invalidates
  // the draft.
  useEffect(() => {
    setDraft(null);
  }, [saved]);

  if (!bounds) return null;

  return (
    <SettingsCard
      id="reveal"
      label="TYPEWRITER"
      footer={
        <>
          <span className={`caption ${dirty ? "warning" : "dim"}`}>
            {dirty ? "● UNSAVED" : ""}
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
    <SettingsCard id="pwa" label="APP ICON">
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
      <div className="eyebrow brass-glow">SETTINGS</div>
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

  return (
    <div className="settings-pane-v2" data-testid="settings-pane">
      <SectionRail active={active} onPick={jumpTo} />
      <div className="set-scroller" ref={scrollerRef}>
        {mutation.isError && (
          <div className="alert danger">
            <AlertTriangle size={14} />
            <div>
              <div className="alert-title">WRITE REJECTED</div>
              <div className="alert-body">{mutation.error.message}</div>
            </div>
          </div>
        )}

        <ThemeSection active={theme as ThemeId} onPick={(t) => setTheme(t)} />
        <TypographySection />
        <TestModeSection
          on={testMode}
          onToggle={(value) => mutation.mutate({ test_mode: value })}
        />
        <ModelSection
          settings={settings}
          onPick={(ref) =>
            mutation.mutate({ apex_model_ref: ref, wizard_model_ref: ref })
          }
        />
        <ContextLengthSection
          settings={settings}
          onCommit={(value) => mutation.mutate({ apex_context_window: value })}
        />
        <TypewriterSection
          settings={settings}
          onCommit={(value) => mutation.mutate({ typewriter_ms_per_char: value })}
        />
        <PwaSection />
      </div>
    </div>
  );
}
