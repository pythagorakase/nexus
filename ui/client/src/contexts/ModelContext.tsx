/**
 * Model selection context for managing LLM model choice across the application.
 *
 * Provides per-call model selection with localStorage persistence.
 * Models are fetched dynamically from /api/config/models to reflect nexus.toml changes.
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

// Model info from API
interface ModelInfo {
  id: string;
  label: string;
  description?: string;  // Optional now
  provider: string;
}

interface ModelContextType {
  model: string;
  setModel: (model: string) => void;
  isTestMode: boolean;
  // Available models for UI picker (fetched from backend)
  availableModels: ModelInfo[];
  // Models grouped by provider (for nested dropdown menus)
  modelsByProvider: Record<string, ModelInfo[]>;
  isLoading: boolean;
}

const ModelContext = createContext<ModelContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-model';
const DEFAULT_MODEL = 'gpt-5.2';

// Fallback models if API fails (matches nexus.toml defaults)
const FALLBACK_MODELS: ModelInfo[] = [
  { id: 'gpt-5.2', label: 'GPT-5.2', provider: 'openai' },
  { id: 'TEST', label: 'TEST', provider: 'test' },
  { id: 'claude', label: 'Claude', provider: 'anthropic' },
];

// Build fallback by_provider from flat list
const FALLBACK_BY_PROVIDER: Record<string, ModelInfo[]> = FALLBACK_MODELS.reduce((acc, m) => {
  if (!acc[m.provider]) acc[m.provider] = [];
  acc[m.provider].push(m);
  return acc;
}, {} as Record<string, ModelInfo[]>);

export function ModelProvider({ children }: { children: ReactNode }) {
  const [model, setModelState] = useState<string>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored || DEFAULT_MODEL;
  });
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>(FALLBACK_MODELS);
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelInfo[]>>(FALLBACK_BY_PROVIDER);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch available models from backend on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        console.log('[ModelContext] Fetching models from API...');
        const response = await fetch('/api/config/models');
        if (response.ok) {
          const data = await response.json();
          console.log('[ModelContext] API response:', data);
          if (data.models && Array.isArray(data.models) && data.models.length > 0) {
            setAvailableModels(data.models);

            // Compute modelsByProvider from the flat models list
            // (more reliable than using by_provider since models already have provider field)
            const byProvider = (data.models as ModelInfo[]).reduce((acc, m) => {
              const provider = m.provider || 'other';
              if (!acc[provider]) acc[provider] = [];
              acc[provider].push(m);
              return acc;
            }, {} as Record<string, ModelInfo[]>);
            console.log('[ModelContext] Computed byProvider:', byProvider);
            setModelsByProvider(byProvider);

            // Validate stored model is still valid
            const validIds = data.models.map((m: ModelInfo) => m.id);
            const storedModel = localStorage.getItem(STORAGE_KEY);
            if (storedModel && !validIds.includes(storedModel)) {
              // Stored model no longer valid, reset to default
              const newDefault = validIds.includes(DEFAULT_MODEL) ? DEFAULT_MODEL : validIds[0];
              setModelState(newDefault);
              localStorage.setItem(STORAGE_KEY, newDefault);
            }
          }
        }
      } catch (error) {
        console.warn('Failed to fetch models from API, using fallback:', error);
        // Keep using fallback models
      } finally {
        setIsLoading(false);
      }
    };

    fetchModels();
  }, []);

  // Persist model selection to localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, model);
  }, [model]);

  const setModel = (newModel: string) => setModelState(newModel);

  const isTestMode = model === 'TEST';

  return (
    <ModelContext.Provider value={{
      model,
      setModel,
      isTestMode,
      availableModels,
      modelsByProvider,
      isLoading,
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
