/**
 * Shared model icon utilities for provider logo/icon rendering.
 *
 * Assets live in /icons/providers/:
 * - openai-wordmark.svg - OpenAI wordmark (for submenu triggers)
 * - openai-icon.svg - OpenAI monoblossom (for model items)
 * - anthropic-logo.svg - Anthropic logo (for submenu triggers)
 * - claude-icon.svg - Claude Spark (for model items)
 */
import { Cpu } from 'lucide-react';

// Provider asset configuration with paths and default sizing
// OpenAI's SVG includes required brand whitespace (~3x padding), Anthropic's is tight.
// We use equal total heights with Anthropic getting CSS padding to compensate.
const providerAssets: Record<string, {
  wordmark: string;
  icon: string;
  wordmarkClass: string;   // Height/width classes for the img
  wrapperClass: string;    // Wrapper div classes (for padding/alignment)
  iconClass: string;
}> = {
  openai: {
    wordmark: '/icons/providers/openai-wordmark.svg',
    icon: '/icons/providers/openai-icon.svg',
    wordmarkClass: 'h-12 w-auto',  // Includes brand-mandated whitespace
    wrapperClass: '',              // No extra padding needed
    iconClass: 'w-5 h-5',
  },
  anthropic: {
    wordmark: '/icons/providers/anthropic-logo.svg',
    icon: '/icons/providers/claude-icon.svg',
    wordmarkClass: 'h-4 w-auto',   // Tight crop, text only
    wrapperClass: 'py-4',          // Add padding to match OpenAI's total height
    iconClass: 'w-5 h-5',
  },
};

// Compact wordmark sizes for smaller UI contexts (toolbars, etc.)
const compactWordmarkConfig: Record<string, { imgClass: string; wrapperClass: string }> = {
  openai: { imgClass: 'h-9 w-auto', wrapperClass: '' },
  anthropic: { imgClass: 'h-3 w-auto', wrapperClass: 'py-3' },
};

/**
 * Get the wordmark/logo element for a provider (used in submenu triggers).
 * Returns null for unknown providers (use fallback text instead).
 * Use compact=true for smaller UI contexts like toolbars.
 * Returns a wrapper div with proper padding to ensure equal heights across providers.
 */
export function getProviderWordmark(provider: string, compact?: boolean): React.ReactElement | null {
  const assets = providerAssets[provider];
  if (!assets) return null;

  let imgClass: string;
  let wrapperClass: string;

  if (compact) {
    const config = compactWordmarkConfig[provider] ?? { imgClass: 'h-3 w-auto', wrapperClass: '' };
    imgClass = config.imgClass;
    wrapperClass = config.wrapperClass;
  } else {
    imgClass = assets.wordmarkClass;
    wrapperClass = assets.wrapperClass;
  }

  return (
    <div className={`flex items-center justify-center ${wrapperClass}`}>
      <img
        src={assets.wordmark}
        alt={provider}
        className={imgClass}
      />
    </div>
  );
}

/**
 * Get the icon element for a provider (used in model items and triggers).
 * Falls back to Cpu icon for unknown providers.
 * If no className provided, uses provider-specific default.
 */
export function getProviderIcon(provider: string, className?: string): React.ReactElement {
  const assets = providerAssets[provider];
  if (!assets) {
    return <Cpu className={className ?? 'w-5 h-5'} />;
  }

  return (
    <img
      src={assets.icon}
      alt=""
      className={className ?? assets.iconClass}
    />
  );
}

/**
 * Get the icon for a specific model by looking up its provider.
 * Requires the modelsByProvider map to find the model's provider.
 * If no className provided, uses provider-specific default.
 */
export function getModelIcon(
  modelId: string,
  modelsByProvider: Record<string, { id: string; provider: string }[]>,
  className?: string
): React.ReactElement {
  // Find which provider this model belongs to
  for (const [provider, models] of Object.entries(modelsByProvider)) {
    if (models.some(m => m.id === modelId)) {
      return getProviderIcon(provider, className);
    }
  }
  // Fallback for unknown models
  return <Cpu className={className ?? 'w-5 h-5'} />;
}
