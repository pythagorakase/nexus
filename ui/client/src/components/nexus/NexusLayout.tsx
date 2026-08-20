/**
 * NexusLayout - the long-lived "reading the story" surface.
 *
 * Composition (NEXUS IRIS design system):
 * - 52px top operator strip (wordmark + slot label / SKALD status)
 * - 60px left icon rail (Home, Narrative, Map, Characters, Settings)
 * - main pane router
 * - 320px right Session Ledger rail on the narrative tab only
 *
 * All data is live: Express read routes for committed narrative and cast,
 * the FastAPI narrative service (proxied) for slot state, generation, and
 * phase telemetry over /ws/narrative.
 */
import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "@/contexts/ThemeContext";
import { useDeveloperMode } from "@/contexts/DeveloperModeContext";
import { useNarrativeEngine } from "@/hooks/useNarrativeEngine";
import { getUserCharacter } from "@/lib/narrative-api";
import type { SettingsPayload } from "@/types/settings";
import { LeftRail, type NexusTab } from "./LeftRail";
import { TopBar } from "./TopBar";
import { NarrativePane } from "./NarrativePane";
import { RightLedger } from "./RightLedger";
import { CharactersPane } from "./CharactersPane";
import { MapPane } from "./MapPane";
import { SettingsPane } from "./SettingsPane";
import { BackstageDrawer } from "./BackstageDrawer";
import "./nexus-layout.css";

const TABS: NexusTab[] = ["narrative", "map", "characters", "settings"];
// Fallback used only until GET /api/settings resolves. Must stay in sync
// with `[ui] typewriter_ms_per_char` in nexus.toml (UISettings default).
const DEFAULT_TYPEWRITER_MS = 35;

function initialTab(): NexusTab {
  const requested = new URLSearchParams(window.location.search).get("tab");
  return TABS.includes(requested as NexusTab)
    ? (requested as NexusTab)
    : "narrative";
}

function activeSlot(): number | null {
  try {
    const stored = localStorage.getItem("activeSlot");
    if (!stored) return null;
    const slot = parseInt(stored, 10);
    return isNaN(slot) ? null : slot;
  } catch {
    return null;
  }
}

export function NexusLayout() {
  const [, setLocation] = useLocation();
  const { isVector } = useTheme();
  const { effectiveDeveloperMode } = useDeveloperMode();
  const [tab, setTab] = useState<NexusTab>(initialTab);
  const [backstageOpen, setBackstageOpen] = useState(false);
  const [slot] = useState<number | null>(activeSlot);
  // Reading position: null = live frontier; a chunk id = historical
  // reading (read-only). Shared by the reader and the right-rail tree.
  const [readingChunkId, setReadingChunkId] = useState<number | null>(null);

  const engine = useNarrativeEngine(slot);

  const { data: userCharacter } = useQuery<{ name: string } | null>({
    queryKey: ["/api/user-character", slot],
    queryFn: () => getUserCharacter(slot as number),
    enabled: slot !== null,
  });

  const { data: settings } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
  });
  const typewriterMsPerChar =
    settings?.ui?.typewriter_ms_per_char ?? DEFAULT_TYPEWRITER_MS;
  const backstagePollBusyMs =
    settings?.orrery?.dashboard?.backstage_poll_busy_ms ?? 2000;
  const backstagePollIdleMs =
    settings?.orrery?.dashboard?.backstage_poll_idle_ms ?? 8000;

  useEffect(() => {
    if (!effectiveDeveloperMode) setBackstageOpen(false);
  }, [effectiveDeveloperMode]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (["INPUT", "TEXTAREA"].includes(target.tagName) || target.isContentEditable)
      ) {
        return;
      }
      if (event.key === "Escape") {
        setBackstageOpen(false);
      } else if (event.key === "`" && effectiveDeveloperMode) {
        setBackstageOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [effectiveDeveloperMode]);

  // Keep ?tab= in the URL so deep links and refreshes restore the pane.
  useEffect(() => {
    const url = tab === "narrative" ? "/nexus" : `/nexus?tab=${tab}`;
    window.history.replaceState(null, "", url);
  }, [tab]);

  const showLedger = tab === "narrative" && slot !== null;

  return (
    <div
      className={`nexus-shell animate-fade-in ${isVector ? "terminal-scanlines" : ""}`}
      data-testid="nexus-layout"
    >
      <TopBar
        slot={slot}
        characterName={userCharacter?.name ?? null}
        skaldStatus={engine.skaldStatus}
      />
      <div className={`nexus-main ${showLedger ? "" : "no-ledger"}`}>
        <LeftRail
          tab={tab}
          onTabChange={setTab}
          onHome={() => setLocation("/")}
          showBackstage={effectiveDeveloperMode}
          backstageOpen={backstageOpen}
          onBackstageToggle={() => setBackstageOpen((open) => !open)}
        />
        <main className="nexus-content">
          {tab === "narrative" &&
            (slot === null ? (
              <div className="pane-notice">
                <span className="notice-text">[ NO ACTIVE SLOT ]</span>
              </div>
            ) : engine.slotStateError ? (
              <div className="pane-notice">
                <span className="notice-text">[ SLOT STATE UNAVAILABLE ]</span>
                <span className="notice-detail">
                  {engine.slotStateError.message}
                </span>
              </div>
            ) : (
              <NarrativePane
                slot={slot}
                engine={engine}
                typewriterMsPerChar={typewriterMsPerChar}
                readingChunkId={readingChunkId}
                onNavigate={setReadingChunkId}
              />
            ))}
          {tab === "map" && <MapPane slot={slot} />}
          {tab === "characters" &&
            (slot === null ? (
              <div className="pane-notice">
                <span className="notice-text">[ NO ACTIVE SLOT ]</span>
              </div>
            ) : (
              <CharactersPane slot={slot} />
            ))}
          {tab === "settings" && <SettingsPane />}
        </main>
        {showLedger && (
          <RightLedger
            slot={slot as number}
            engine={engine}
            readingChunkId={readingChunkId}
            onNavigate={setReadingChunkId}
          />
        )}
        {effectiveDeveloperMode && backstageOpen && slot !== null && (
          <BackstageDrawer
            slot={slot}
            onClose={() => setBackstageOpen(false)}
            pollBusyMs={backstagePollBusyMs}
            pollIdleMs={backstagePollIdleMs}
          />
        )}
      </div>
    </div>
  );
}
