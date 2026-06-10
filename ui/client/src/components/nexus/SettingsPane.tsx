/**
 * SettingsPane - kit-fidelity placeholder (full settings wiring is U5).
 *
 * The theme picker is live (ThemeContext persists to localStorage today);
 * the remaining rows are read-only values from GET /api/settings so the
 * operator can verify configuration at a glance.
 */
import { useQuery } from "@tanstack/react-query";
import { useTheme, type Theme } from "@/contexts/ThemeContext";
import type { SettingsPayload } from "@/types/settings";

/** Palette swatches from the NEXUS IRIS theme matrix (display-only). */
const THEME_CARDS: Array<{
  id: Theme;
  name: string;
  motto: string;
  swatches: string[];
}> = [
  {
    id: "veil",
    name: "Veil",
    motto: "Magenta rain on blue-black",
    swatches: ["#09101c", "#b83d7a", "#e86a4a", "#e1cd97"],
  },
  {
    id: "gilded",
    name: "Gilded",
    motto: "Brass engraved on midnight",
    swatches: ["#0a0a0a", "#c9a227", "#7b5524", "#ece2c1"],
  },
  {
    id: "vector",
    name: "Vector",
    motto: "Scanline void · on the wire",
    swatches: ["#031414", "#00e5ff", "#3aa1ff", "#a3f0ff"],
  },
];

export function SettingsPane() {
  const { theme, setTheme } = useTheme();

  const { data: settings } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
  });

  const defaultModel =
    settings?.["Agent Settings"]?.global?.model?.default_model ?? "—";
  const testMode = settings?.["Agent Settings"]?.global?.narrative?.test_mode;
  const typeSpeed = settings?.ui?.typewriter_ms_per_char;

  return (
    <div className="settings-pane" data-testid="settings-pane">
      <div className="settings-card">
        <div className="settings-inner">
          <span className="eyebrow brass-glow">[ APPEARANCE ]</span>
          <h2 className="settings-title">Theme</h2>
          <div className="theme-cards">
            {THEME_CARDS.map((card) => (
              <button
                key={card.id}
                className={`theme-card ${theme === card.id ? "on" : ""}`}
                onClick={() => setTheme(card.id)}
                data-testid={`theme-${card.id}`}
              >
                <span className="theme-name">
                  {card.name}
                  {theme === card.id ? " ✓" : ""}
                </span>
                <span className="theme-motto">{card.motto}</span>
                <span className="theme-swatches">
                  {card.swatches.map((color) => (
                    <span key={color} style={{ background: color }} />
                  ))}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-inner">
          <span className="eyebrow brass-glow">[ CONFIGURATION ]</span>
          <h2 className="settings-title">Readout</h2>
          <div className="set-row">
            <span className="set-label">Default Model</span>
            <span className="set-val" data-testid="text-setting-model">
              {defaultModel}
            </span>
          </div>
          <div className="set-row">
            <span className="set-label">Test Mode</span>
            <span className="set-val">
              {testMode === undefined ? "—" : testMode ? "ENABLED" : "OFF"}
            </span>
          </div>
          <div className="set-row">
            <span className="set-label">Typewriter Speed</span>
            <span className="set-val">
              {typeSpeed !== undefined ? `${typeSpeed} ms/char` : "—"}
            </span>
          </div>
          <div className="set-row">
            <span className="set-label">Calibration Console</span>
            <span className="set-val">ARRIVING · U5</span>
          </div>
        </div>
      </div>
    </div>
  );
}
