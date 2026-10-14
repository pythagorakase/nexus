import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePlane } from "@/hooks/usePlane";

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
  const [developerMode, setDeveloperModeState] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true",
  );
  const { data: gateOpen = false } = useQuery<boolean>({
    queryKey: ["/api/dev/backstage/health"],
    queryFn: async () => {
      try {
        const response = await fetch("/api/dev/backstage/health");
        return response.status === 200;
      } catch {
        return false;
      }
    },
    retry: false,
    staleTime: Infinity,
    // The backstage gate is an operator route (#824); closed until it answers.
    enabled: usePlane() === "operator",
  });

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
