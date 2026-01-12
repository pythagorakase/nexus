/**
 * Model selection context for managing LLM model choice across the application.
 *
 * Provides per-call model selection with localStorage persistence.
 * Available models: gpt-5.1 (default), TEST (mock server), claude (future)
 *
 * The TEST model can be hidden from the UI picker by setting showTestModel=false.
 * This is controlled by the `test_mode` setting in nexus.toml - it's purely a
 * visibility flag; the TEST model still works if passed directly via API/CLI.
 */
import { createContext, useContext, useState, useEffect, useMemo, ReactNode } from 'react';

export type Model = 'gpt-5.1' | 'TEST' | 'claude';

interface ModelContextType {
  model: Model;
  setModel: (model: Model) => void;
  isTestMode: boolean;
  // Available models for UI picker (filtered by visibility settings)
  availableModels: { id: Model; label: string; description: string }[];
}

interface ModelProviderProps {
  children: ReactNode;
  /** Whether to show TEST model in the picker. Default: true */
  showTestModel?: boolean;
}

const ModelContext = createContext<ModelContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-model';
const DEFAULT_MODEL: Model = 'gpt-5.1';

// All models (visibility may be filtered)
const ALL_MODELS: { id: Model; label: string; description: string }[] = [
  { id: 'gpt-5.1', label: 'GPT-5.1', description: 'OpenAI GPT-5.1 (production)' },
  { id: 'TEST', label: 'TEST', description: 'Mock server with cached data (dev)' },
  { id: 'claude', label: 'Claude', description: 'Anthropic Claude (coming soon)' },
];

export function ModelProvider({ children, showTestModel: showTestModelProp }: ModelProviderProps) {
  const [model, setModelState] = useState<Model>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Validate stored value is a valid model
    if (stored === 'gpt-5.1' || stored === 'TEST' || stored === 'claude') {
      return stored;
    }
    return DEFAULT_MODEL;
  });

  // Fetch visibility setting from backend (test_mode controls TEST model visibility)
  const [showTestModelFromSettings, setShowTestModelFromSettings] = useState(true);

  useEffect(() => {
    // Fetch settings to check if TEST model should be visible
    fetch('/api/settings')
      .then(res => res.json())
      .then(settings => {
        // test_mode in settings controls whether TEST is visible in the picker
        const visible = Boolean(settings?.['Agent Settings']?.global?.narrative?.test_mode ?? true);
        setShowTestModelFromSettings(visible);
      })
      .catch(() => {
        // On error, default to showing TEST model
        setShowTestModelFromSettings(true);
      });
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, model);
  }, [model]);

  const setModel = (newModel: Model) => setModelState(newModel);

  const isTestMode = model === 'TEST';

  // Use prop override if provided, otherwise use settings
  const showTestModel = showTestModelProp ?? showTestModelFromSettings;

  // Filter available models based on visibility settings
  const availableModels = useMemo(() => {
    if (showTestModel) {
      return ALL_MODELS;
    }
    return ALL_MODELS.filter(m => m.id !== 'TEST');
  }, [showTestModel]);

  return (
    <ModelContext.Provider value={{
      model,
      setModel,
      isTestMode,
      availableModels,
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
