import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useSettingsQuery } from "@/hooks/useSettings";

interface DeveloperModeContextType {
  gateOpen: boolean;
  developerMode: boolean;
  effectiveDeveloperMode: boolean;
  setDeveloperMode: (enabled: boolean) => void;
}

const DeveloperModeContext = createContext<DeveloperModeContextType | undefined>(
  undefined,
);

const STORAGE_KEY = "nexus-developer-mode";

export function DeveloperModeProvider({ children }: { children: ReactNode }) {
  const { data: settings } = useSettingsQuery();
  const [developerMode, setDeveloperModeState] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true",
  );
  const gateOpen = settings?.orrery?.dashboard?.enabled === true;

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(developerMode));
  }, [developerMode]);

  return (
    <DeveloperModeContext.Provider
      value={{
        gateOpen,
        developerMode,
        effectiveDeveloperMode: gateOpen && developerMode,
        setDeveloperMode: setDeveloperModeState,
      }}
    >
      {children}
    </DeveloperModeContext.Provider>
  );
}

export function useDeveloperMode(): DeveloperModeContextType {
  const context = useContext(DeveloperModeContext);
  if (!context) {
    throw new Error("useDeveloperMode must be used within DeveloperModeProvider");
  }
  return context;
}
