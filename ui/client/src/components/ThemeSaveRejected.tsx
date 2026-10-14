import { useEffect, useRef, type CSSProperties } from "react";
import { AlertTriangle } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";

/**
 * The Settings card's danger alert reads --danger, which nexus-layout.css
 * defines only inside the Settings pane; a menu portal sits outside it, so
 * map the same token here.
 */
const MENU_ALERT_STYLE = { "--danger": "hsl(var(--destructive))" } as CSSProperties;

/**
 * The Settings THEME card's WRITE REJECTED alert, for theme menus outside the
 * Settings pane. Renders nothing while the last theme save succeeded.
 */
export function ThemeSaveRejected({ testId }: { testId: string }) {
  const { saveError } = useTheme();
  if (saveError === null) return null;
  return (
    <div
      className="alert danger mt-1 max-w-[280px] break-words"
      role="alert"
      data-testid={testId}
      style={MENU_ALERT_STYLE}
    >
      <AlertTriangle size={14} />
      <div className="min-w-0">
        <div className="alert-title">WRITE REJECTED</div>
        <div className="alert-body">{saveError}</div>
      </div>
    </div>
  );
}

/**
 * Opens a theme menu when a theme save is rejected, so the reason shows where
 * the pick happened. A menu that mounts while a rejection is still held opens
 * as well, so a save that failed while the player was elsewhere is shown on
 * return. The rejection is held until a later save succeeds or the Settings
 * THEME card mounts.
 */
export function useOpenOnThemeSaveError(setOpen: (open: boolean) => void): void {
  const { saveError } = useTheme();
  const lastError = useRef<string | null>(null);

  useEffect(() => {
    if (saveError !== null && lastError.current === null) setOpen(true);
    lastError.current = saveError;
  }, [saveError, setOpen]);
}
