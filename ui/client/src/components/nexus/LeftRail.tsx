/**
 * LeftRail - the 60px vertical icon rail (primary navigation).
 *
 * Home returns to the splash; the four tabs switch the main pane. The
 * active tab carries the 3x22px magenta edge marker + glow (CSS ::before).
 * Lucide icons inherit color from the surrounding text per the README.
 */
import { Book, Home, Map, Settings, Users } from "lucide-react";

export type NexusTab = "narrative" | "map" | "characters" | "settings";

const RAIL_TABS: Array<{ id: NexusTab; label: string; Icon: typeof Book }> = [
  { id: "narrative", label: "Narrative", Icon: Book },
  { id: "map", label: "Map", Icon: Map },
  { id: "characters", label: "Characters", Icon: Users },
  { id: "settings", label: "Settings", Icon: Settings },
];

interface LeftRailProps {
  tab: NexusTab;
  onTabChange: (tab: NexusTab) => void;
  onHome: () => void;
}

export function LeftRail({ tab, onTabChange, onHome }: LeftRailProps) {
  return (
    <nav className="rail-left" aria-label="Primary navigation">
      {/* No title attributes: the styled .rail-tip is the hover label, and
          a native tooltip on top of it would restate it (tenet 3). The tip
          hides via opacity (so it never left the accessibility tree), but
          each button also carries an explicit aria-label so its accessible
          name does not depend on a presentation class. */}
      <button
        className="rail-btn"
        onClick={onHome}
        aria-label="Home"
        data-testid="rail-home"
      >
        <Home size={18} />
        <span className="rail-tip" aria-hidden="true">
          HOME
        </span>
      </button>
      <div className="rail-divider" />
      {RAIL_TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          className={`rail-btn ${tab === id ? "on" : ""}`}
          onClick={() => onTabChange(id)}
          aria-label={label}
          aria-pressed={tab === id}
          data-testid={`rail-${id}`}
        >
          <Icon size={18} />
          <span className="rail-tip" aria-hidden="true">
            {label.toUpperCase()}
          </span>
        </button>
      ))}
      <div className="rail-spacer" />
      <div className="rail-monogram" aria-hidden="true">
        N·I
      </div>
    </nav>
  );
}
