/**
 * Settings page for customizing font preferences, PWA icon, and backend settings.
 */
import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useFonts } from '@/contexts/FontContext';
import { useTheme, type Theme } from '@/contexts/ThemeContext';
import { useModel, Model } from '@/contexts/ModelContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2, Upload, Save, AlertCircle, Sparkles, Monitor, Wand2, Palette, Cpu } from 'lucide-react';
import { PaletteComparison } from '@/components/PaletteComparison';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';

// Gilded theme fonts - elegant Art Deco options
const GILDED_BODY_FONTS = [
  'Cormorant Garamond',
  'Libre Baskerville',
];

const GILDED_MENU_FONTS = [
  'Space Mono',
];

// Vector theme fonts - body text options (sans-serif for readability)
const VECTOR_NARRATIVE_FONTS = [
  'Rajdhani',
  'Jura',
];

const VECTOR_UI_FONTS = [
  'Source Code Pro',
  'Courier Prime',
  'Monaco',
  'Consolas',
];

// Veil theme fonts - Art Nouveau elegance
const VEIL_BODY_FONTS = [
  'Spectral',
  'Cormorant Garamond',
];

const VEIL_UI_FONTS = [
  'Cinzel',  // Used with small-caps; non-mono so layouts need fixed widths
];

// Display fonts - decorative fonts for headings and large text
const GILDED_DISPLAY_FONTS = [
  'Monoton',
  'Major Mono Display',
];

const VECTOR_DISPLAY_FONTS = [
  'Sixtyfour',
];

const VEIL_DISPLAY_FONTS = [
  'Megrim',
];

export function SettingsTab() {
  const {
    fonts,
    setCyberpunkNarrativeFont,
    setCyberpunkUIFont,
    setCyberpunkDisplayFont,
    setGildedBodyFont,
    setGildedMenuFont,
    setGildedDisplayFont,
    setVeilBodyFont,
    setVeilMenuFont,
    setVeilDisplayFont,
    resetToDefaults,
    currentBodyFont,
    currentMenuFont,
    currentDisplayFont,
  } = useFonts();
  const { theme, setTheme, isGilded, isVector, isVeil } = useTheme();
  const { model, setModel, availableModels } = useModel();
  const queryClient = useQueryClient();
  const glowClass = isGilded ? "deco-glow" : isVeil ? "veil-glow" : "terminal-glow";
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Backend settings state
  const [apexContextWindow, setApexContextWindow] = useState<number>(100000);
  const [originalApexContextWindow, setOriginalApexContextWindow] = useState<number>(100000);
  const [testModeEnabled, setTestModeEnabled] = useState(false);
  const [testDatabaseSuffix, setTestDatabaseSuffix] = useState<string>("_test");
  const [savingSettings, setSavingSettings] = useState(false);
  const [updatingTestMode, setUpdatingTestMode] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loadingSettings, setLoadingSettings] = useState(true);

  // Load current settings on mount
  useEffect(() => {
    async function loadSettings() {
      try {
        const response = await fetch('/api/settings');
        if (!response.ok) throw new Error('Failed to load settings');
        const settings = await response.json();
        const contextWindow = settings?.['Agent Settings']?.LORE?.token_budget?.apex_context_window || 100000;
        setApexContextWindow(contextWindow);
        setOriginalApexContextWindow(contextWindow);
        const narrativeSettings = settings?.['Agent Settings']?.global?.narrative || {};
        setTestModeEnabled(Boolean(narrativeSettings.test_mode));
        if (typeof narrativeSettings.test_database_suffix === 'string') {
          setTestDatabaseSuffix(narrativeSettings.test_database_suffix);
        }
      } catch (error) {
        console.error('Error loading settings:', error);
        setSettingsMessage({ type: 'error', text: 'Failed to load backend settings' });
      } finally {
        setLoadingSettings(false);
      }
    }
    loadSettings();
  }, []);

  const handleToggleTestMode = async (value: boolean) => {
    const previous = testModeEnabled;
    setTestModeEnabled(value);
    setUpdatingTestMode(true);
    setSettingsMessage(null);

    try {
      const response = await fetch('/api/settings', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          'Agent Settings': {
            global: {
              narrative: {
                test_mode: value,
              },
            },
          },
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to update test mode');
      }

      const payload = await response.json();
      if (payload?.settings) {
        queryClient.setQueryData(["/api/settings"], payload.settings);
      }

      setSettingsMessage({
        type: 'success',
        text: value
          ? 'Test Narrative Mode enabled (using parallel test tables)'
          : 'Test Narrative Mode disabled',
      });
    } catch (error) {
      console.error('Error updating test mode:', error);
      setTestModeEnabled(previous);
      setSettingsMessage({
        type: 'error',
        text: error instanceof Error ? error.message : 'Failed to update test mode',
      });
    } finally {
      setUpdatingTestMode(false);
    }
  };

  const handleIconSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      setIconFile(file);
      const reader = new FileReader();
      reader.onload = (e) => {
        setIconPreview(e.target?.result as string);
      };
      reader.readAsDataURL(file);
      setUploadMessage(null);
    }
  };

  const handleIconUpload = async () => {
    if (!iconFile) return;

    setUploading(true);
    setUploadMessage(null);

    try {
      const formData = new FormData();
      formData.append('icon', iconFile);

      const response = await fetch('/api/settings/pwa-icon', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to upload icon');
      }

      setUploadMessage({ type: 'success', text: 'PWA icon updated successfully! Refresh to see changes.' });
      setIconFile(null);
      setIconPreview(null);
    } catch (error) {
      setUploadMessage({
        type: 'error',
        text: error instanceof Error ? error.message : 'Failed to upload icon'
      });
    } finally {
      setUploading(false);
    }
  };

  const handleSaveApexContextWindow = async () => {
    setSavingSettings(true);
    setSettingsMessage(null);

    try {
      const response = await fetch('/api/settings', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          'Agent Settings': {
            LORE: {
              token_budget: {
                apex_context_window: apexContextWindow,
              },
            },
          },
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to update settings');
      }

      try {
        const payload = await response.json();
        if (payload?.settings) {
          queryClient.setQueryData(["/api/settings"], payload.settings);
        }
      } catch (err) {
        console.warn('Unable to update cache after saving settings', err);
      }

      setOriginalApexContextWindow(apexContextWindow);
      setSettingsMessage({ type: 'success', text: 'Context window updated successfully!' });
    } catch (error) {
      setSettingsMessage({
        type: 'error',
        text: error instanceof Error ? error.message : 'Failed to update settings'
      });
    } finally {
      setSavingSettings(false);
    }
  };

  const hasUnsavedChanges = apexContextWindow !== originalApexContextWindow;

  return (
  <>
    <ScrollArea className="h-full min-h-0 w-full">
      <div className="container max-w-4xl py-8 px-6 space-y-6">
        <div className="space-y-2">
          <h2
            className={`text-2xl font-bold text-primary ${glowClass}`}
            style={{ fontFamily: currentDisplayFont }}
          >
            Settings
          </h2>
          <p className="text-muted-foreground font-mono text-sm pl-1">
            Customize typography and appearance preferences
          </p>
        </div>

        {/* Theme Selection */}
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="font-mono">Theme</CardTitle>
                <CardDescription className="font-mono text-xs">
                  Choose the visual style for the interface
                </CardDescription>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 -mt-1 text-muted-foreground hover:text-primary"
                onClick={() => setPaletteOpen(true)}
                title="View palette comparison"
              >
                <Palette className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <RadioGroup
              value={theme}
              onValueChange={(value: Theme) => setTheme(value)}
              className="grid grid-cols-3 gap-4"
            >
              <Label
                htmlFor="theme-gilded"
                className={`flex flex-col items-center justify-between rounded-md border-2 p-4 cursor-pointer hover:bg-accent/10 transition-colors ${isGilded ? "border-primary bg-primary/5" : "border-muted"
                  }`}
              >
                <RadioGroupItem value="gilded" id="theme-gilded" className="sr-only" />
                <Sparkles className={`mb-3 h-6 w-6 ${isGilded ? "text-primary" : "text-muted-foreground"}`} />
                <span className={`font-mono text-sm font-semibold ${isGilded ? "text-primary" : ""}`}>
                  Gilded
                </span>
                <span className="font-mono text-xs text-muted-foreground mt-1">
                  Art Deco elegance
                </span>
              </Label>
              <Label
                htmlFor="theme-vector"
                className={`flex flex-col items-center justify-between rounded-md border-2 p-4 cursor-pointer hover:bg-accent/10 transition-colors ${isVector ? "border-primary bg-primary/5" : "border-muted"
                  }`}
              >
                <RadioGroupItem value="vector" id="theme-vector" className="sr-only" />
                <Monitor className={`mb-3 h-6 w-6 ${isVector ? "text-primary" : "text-muted-foreground"}`} />
                <span className={`font-mono text-sm font-semibold ${isVector ? "text-primary" : ""}`}>
                  Vector
                </span>
                <span className="font-mono text-xs text-muted-foreground mt-1">
                  Terminal aesthetic
                </span>
              </Label>
              <Label
                htmlFor="theme-veil"
                className={`flex flex-col items-center justify-between rounded-md border-2 p-4 cursor-pointer hover:bg-accent/10 transition-colors ${isVeil ? "border-primary bg-primary/5" : "border-muted"
                  }`}
              >
                <RadioGroupItem value="veil" id="theme-veil" className="sr-only" />
                <Wand2 className={`mb-3 h-6 w-6 ${isVeil ? "text-primary" : "text-muted-foreground"}`} />
                <span className={`font-mono text-sm font-semibold ${isVeil ? "text-primary" : ""}`}>
                  Veil
                </span>
                <span className="font-mono text-xs text-muted-foreground mt-1">
                  Art Nouveau mystique
                </span>
              </Label>
            </RadioGroup>
          </CardContent>
        </Card>

        {/* Typography - Subordinate to Theme */}
        <Card>
          <CardHeader>
            <CardTitle className="font-mono">Typography</CardTitle>
            <CardDescription className="font-mono text-xs">
              {isGilded
                ? "Elegant serif options for the Gilded theme"
                : isVeil
                  ? "Art Nouveau typography for the Veil theme"
                  : "Terminal fonts for the Vector aesthetic"
              }
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {isGilded ? (
              <>
                {/* Gilded Body Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="gilded-body-font" className="font-mono text-sm">
                    Body Text
                  </Label>
                  <Select
                    value={fonts.gildedBodyFont}
                    onValueChange={setGildedBodyFont}
                  >
                    <SelectTrigger id="gilded-body-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GILDED_BODY_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm leading-relaxed border border-border"
                    style={{ fontFamily: currentBodyFont }}
                  >
                    Gatsby believed in the green light, the orgastic future that year by year recedes before us.
                  </div>
                </div>

                {/* Gilded Menu Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="gilded-menu-font" className="font-mono text-sm">
                    Menu &amp; Labels
                  </Label>
                  <Select
                    value={fonts.gildedMenuFont}
                    onValueChange={setGildedMenuFont}
                  >
                    <SelectTrigger id="gilded-menu-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GILDED_MENU_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm border border-border tracking-wider"
                    style={{ fontFamily: currentMenuFont }}
                  >
                    STATUS: READY // CHAPTER: S01-E01-S001
                  </div>
                </div>

                {/* Gilded Display Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="gilded-display-font" className="font-mono text-sm">
                    Display Text
                  </Label>
                  <Select
                    value={fonts.gildedDisplayFont}
                    onValueChange={setGildedDisplayFont}
                  >
                    <SelectTrigger id="gilded-display-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GILDED_DISPLAY_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview - larger text for display font */}
                  <div
                    className="p-4 rounded-md bg-muted/50 text-2xl text-center tracking-wider border border-border"
                    style={{ fontFamily: currentDisplayFont }}
                  >
                    NEXUS IRIS
                  </div>
                  <p className="text-xs text-muted-foreground font-mono">
                    For decorative headings and large display text
                  </p>
                </div>
              </>
            ) : isVeil ? (
              <>
                {/* Veil Body Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="veil-body-font" className="font-mono text-sm">
                    Body Text
                  </Label>
                  <Select
                    value={fonts.veilBodyFont}
                    onValueChange={setVeilBodyFont}
                  >
                    <SelectTrigger id="veil-body-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VEIL_BODY_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm leading-relaxed border border-border"
                    style={{ fontFamily: currentBodyFont }}
                  >
                    The night air shimmered with possibility as lanterns cast warm halos through the mist-laden gardens.
                  </div>
                </div>

                {/* Veil Menu Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="veil-menu-font" className="font-mono text-sm">
                    Menu &amp; Labels
                  </Label>
                  <Select
                    value={fonts.veilMenuFont}
                    onValueChange={setVeilMenuFont}
                  >
                    <SelectTrigger id="veil-menu-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VEIL_UI_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm border border-border tracking-wider"
                    style={{ fontFamily: currentMenuFont, fontVariant: 'small-caps' }}
                  >
                    STATUS: READY // CHAPTER: S01-E01-S001
                  </div>
                </div>

                {/* Veil Display Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="veil-display-font" className="font-mono text-sm">
                    Display Text
                  </Label>
                  <Select
                    value={fonts.veilDisplayFont}
                    onValueChange={setVeilDisplayFont}
                  >
                    <SelectTrigger id="veil-display-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VEIL_DISPLAY_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview - larger text for display font */}
                  <div
                    className="p-4 rounded-md bg-muted/50 text-2xl text-center tracking-wider border border-border"
                    style={{ fontFamily: currentDisplayFont }}
                  >
                    NEXUS IRIS
                  </div>
                  <p className="text-xs text-muted-foreground font-mono">
                    For decorative headings and large display text
                  </p>
                </div>
              </>
            ) : (
              <>
                {/* Vector Narrative Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="vector-narrative-font" className="font-mono text-sm">
                    Narrative Text
                  </Label>
                  <Select
                    value={fonts.vectorNarrativeFont}
                    onValueChange={setCyberpunkNarrativeFont}
                  >
                    <SelectTrigger id="vector-narrative-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VECTOR_NARRATIVE_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm leading-relaxed border border-border"
                    style={{ fontFamily: currentBodyFont }}
                  >
                    The rain hammered against the neon-lit windows of the megastructure. Chrome towers pierced the smog-choked sky.
                  </div>
                </div>

                {/* Vector UI Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="vector-ui-font" className="font-mono text-sm">
                    UI Text
                  </Label>
                  <Select
                    value={fonts.vectorUIFont}
                    onValueChange={setCyberpunkUIFont}
                  >
                    <SelectTrigger id="vector-ui-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VECTOR_UI_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview */}
                  <div
                    className="p-3 rounded-md bg-muted/50 text-sm border border-border"
                    style={{ fontFamily: currentMenuFont }}
                  >
                    [STATUS: READY] // APEX: ONLINE // CHAPTER: S01-E01-S001
                  </div>
                </div>

                {/* Vector Display Font with inline preview */}
                <div className="space-y-3">
                  <Label htmlFor="vector-display-font" className="font-mono text-sm">
                    Display Text
                  </Label>
                  <Select
                    value={fonts.vectorDisplayFont}
                    onValueChange={setCyberpunkDisplayFont}
                  >
                    <SelectTrigger id="vector-display-font" className="font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {VECTOR_DISPLAY_FONTS.map((font) => (
                        <SelectItem key={font} value={font} className="font-mono">
                          <span style={{ fontFamily: font }}>{font}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Inline preview - larger text for display font */}
                  <div
                    className="p-4 rounded-md bg-muted/50 text-2xl text-center tracking-wider border border-border"
                    style={{ fontFamily: currentDisplayFont }}
                  >
                    NEXUS IRIS
                  </div>
                  <p className="text-xs text-muted-foreground font-mono">
                    For decorative headings and large display text
                  </p>
                </div>
              </>
            )}

            {/* Reset Button */}
            <div className="pt-4">
              <Button
                onClick={resetToDefaults}
                variant="outline"
                className="font-mono"
              >
                Reset to Defaults
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="font-mono">Narrative Mode</CardTitle>
            <CardDescription className="font-mono text-xs">
              Toggle test routing for live narrative turns.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-1">
                <Label htmlFor="test-mode-toggle" className="font-mono text-sm">
                  Test Narrative Mode
                </Label>
                <p className="text-xs text-muted-foreground font-mono">
                  Writes provisional turns to tables suffixed with <span className="text-primary">{testDatabaseSuffix}</span> so production data stays untouched.
                </p>
              </div>
              <div className="flex items-center gap-3">
                {updatingTestMode && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                <Switch
                  id="test-mode-toggle"
                  checked={testModeEnabled}
                  disabled={updatingTestMode || loadingSettings}
                  onCheckedChange={handleToggleTestMode}
                />
              </div>
            </div>

            {testModeEnabled && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription className="font-mono text-xs">
                  TEST MODE ON - new narrative turns will go to the isolated test tables until you switch back.
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        {/* Model Selection */}
        <Card>
          <CardHeader>
            <CardTitle className="font-mono">Model Selection</CardTitle>
            <CardDescription className="font-mono text-xs">
              Choose the default LLM model for wizard and narrative interactions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <Label htmlFor="default-model" className="font-mono text-sm">
                Default Model
              </Label>
              <Select value={model} onValueChange={(value) => setModel(value as Model)}>
                <SelectTrigger id="default-model" className="font-mono">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4" />
                    <SelectValue />
                  </div>
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((m) => (
                    <SelectItem key={m.id} value={m.id} className="font-mono">
                      <div className="flex flex-col">
                        <span>{m.label}</span>
                        <span className="text-xs text-muted-foreground">{m.description}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground font-mono">
                This model will be used for all LLM calls unless overridden in the chat interface.
                Select TEST to use the mock server for development.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* LORE Settings Section */}
        <Card>
          <CardHeader>
            <CardTitle className="font-mono">LORE Agent Settings</CardTitle>
            <CardDescription className="font-mono text-xs">
              Configure token budgets and context assembly parameters
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {loadingSettings ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                {/* Apex Context Window */}
                <div className="space-y-3">
                  <Label htmlFor="apex-context-window" className="font-mono text-sm">
                    Apex Context Window (tokens)
                  </Label>
                  <Input
                    id="apex-context-window"
                    type="number"
                    value={apexContextWindow}
                    onChange={(e) => setApexContextWindow(parseInt(e.target.value) || 0)}
                    className="font-mono"
                    min="10000"
                    max="200000"
                    step="1000"
                  />
                  <p className="text-xs text-muted-foreground font-mono">
                    Maximum tokens available for context assembly. Smaller values create more compact contexts.
                    <br />
                    Recommended: 100000 for balanced performance, 75000 for compact mode.
                  </p>
                </div>

                {/* Save Button and Messages */}
                <div className="space-y-3">
                  <Button
                    onClick={handleSaveApexContextWindow}
                    disabled={!hasUnsavedChanges || savingSettings}
                    className="font-mono"
                  >
                    {savingSettings ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="mr-2 h-4 w-4" />
                        Save Settings
                      </>
                    )}
                  </Button>

                  {hasUnsavedChanges && !settingsMessage && (
                    <Alert>
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription className="font-mono text-xs">
                        You have unsaved changes
                      </AlertDescription>
                    </Alert>
                  )}

                  {settingsMessage && (
                    <Alert variant={settingsMessage.type === 'error' ? 'destructive' : 'default'}>
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription className="font-mono text-xs">
                        {settingsMessage.text}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* PWA Icon Section */}
        <Card>
          <CardHeader>
            <CardTitle className="font-mono">PWA Icon</CardTitle>
            <CardDescription className="font-mono text-xs">
              Customize the icon that appears on your home screen and dock
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-start gap-4">
              {/* Current Icon Preview */}
              <div className="flex-shrink-0">
                <Label className="font-mono text-sm mb-2 block">Current Icon:</Label>
                <div className="w-24 h-24 rounded-lg border border-border bg-muted/50 flex items-center justify-center overflow-hidden">
                  <img
                    src="/icons/icon-192.png"
                    alt="Current PWA icon"
                    className="w-full h-full object-cover"
                  />
                </div>
              </div>

              {/* Upload Section */}
              <div className="flex-1 space-y-3">
                <div>
                  <Label htmlFor="icon-upload" className="font-mono text-sm mb-2 block">
                    Upload New Icon:
                  </Label>
                  <Input
                    id="icon-upload"
                    type="file"
                    accept="image/png,image/jpeg,image/jpg"
                    onChange={handleIconSelect}
                    className="font-mono cursor-pointer"
                  />
                  <p className="text-xs text-muted-foreground font-mono mt-1">
                    PNG or JPEG, recommended 512x512 or larger
                  </p>
                </div>

                {/* Preview of selected file */}
                {iconPreview && (
                  <div>
                    <Label className="font-mono text-sm mb-2 block">Preview:</Label>
                    <div className="w-24 h-24 rounded-lg border border-border bg-muted/50 flex items-center justify-center overflow-hidden">
                      <img
                        src={iconPreview}
                        alt="Icon preview"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  </div>
                )}

                {/* Upload Button */}
                <Button
                  onClick={handleIconUpload}
                  disabled={!iconFile || uploading}
                  className="font-mono"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="mr-2 h-4 w-4" />
                      Upload Icon
                    </>
                  )}
                </Button>

                {/* Upload Message */}
                {uploadMessage && (
                  <p
                    className={`text-xs font-mono ${uploadMessage.type === 'success' ? 'text-primary' : 'text-destructive'
                      }`}
                  >
                    {uploadMessage.text}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

      </div>
    </ScrollArea>

    <PaletteComparison open={paletteOpen} onOpenChange={setPaletteOpen} />
  </>
  );
}
