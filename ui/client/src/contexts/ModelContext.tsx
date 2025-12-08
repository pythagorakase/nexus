/**
 * Model selection context for managing LLM model choice across the application.
 *
 * Provides per-call model selection with localStorage persistence.
 * Available models: gpt-5.1 (default), TEST (mock server), claude (future)
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Model = 'gpt-5.1' | 'TEST' | 'claude';

interface ModelContextType {
  model: Model;
  setModel: (model: Model) => void;
  isTestMode: boolean;
  // Available models for UI picker
  availableModels: { id: Model; label: string; description: string }[];
}

const ModelContext = createContext<ModelContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-model';
const DEFAULT_MODEL: Model = 'gpt-5.1';

// Models available in the UI picker
const AVAILABLE_MODELS: { id: Model; label: string; description: string }[] = [
  { id: 'gpt-5.1', label: 'GPT-5.1', description: 'OpenAI GPT-5.1 (production)' },
  { id: 'TEST', label: 'TEST', description: 'Mock server with cached data (dev)' },
  { id: 'claude', label: 'Claude', description: 'Anthropic Claude (coming soon)' },
];

export function ModelProvider({ children }: { children: ReactNode }) {
  const [model, setModelState] = useState<Model>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Validate stored value is a valid model
    if (stored === 'gpt-5.1' || stored === 'TEST' || stored === 'claude') {
      return stored;
    }
    return DEFAULT_MODEL;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, model);
  }, [model]);

  const setModel = (newModel: Model) => setModelState(newModel);

  const isTestMode = model === 'TEST';

  return (
    <ModelContext.Provider value={{
      model,
      setModel,
      isTestMode,
      availableModels: AVAILABLE_MODELS,
    }}>
      {children}
    </ModelContext.Provider>
  );
}

export function useModel() {
  const context = useContext(ModelContext);
  if (!context) throw new Error('useModel must be used within ModelProvider');
  return context;
}
