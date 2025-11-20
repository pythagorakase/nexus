/**
 * Settings page for customizing font preferences, PWA icon, and backend settings.
 */
import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useFonts } from '@/contexts/FontContext';
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
import { Loader2, Upload, Save, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';

// Full font list for narrative text
const NARRATIVE_FONTS = [
  'Source Code Pro',
  'Georgia',
  'Lora',
  'Merriweather',
  'Crimson Text',
  'Spectral',
  'Literata',
  'Newsreader',
  'EB Garamond',
  'PT Serif',
  'Libre Baskerville',
  'Inter',
  'Noto Sans',
  'Source Sans 3',
  'Open Sans',
  'Lato',
];

// Fixed-width fonts only for UI text
const UI_FONTS = [
  'Source Code Pro',
  'Courier Prime',
  'Courier New',
  'Monaco',
  'Consolas',
];

export function SettingsTab() {
  const { fonts, setNarrativeFont, setUIFont, resetToDefaults } = useFonts();
  const queryClient = useQueryClient();
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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
    <ScrollArea className="h-full">
      <div className="container max-w-4xl py-8 px-6 space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-mono font-bold text-primary terminal-glow">Settings</h2>
          <p className="text-muted-foreground font-mono text-sm pl-1">
            Customize typography and appearance preferences
          </p>
        </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono">Typography</CardTitle>
          <CardDescription className="font-mono text-xs">
            Choose fonts for different parts of the interface
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Narrative Text Font */}
          <div className="space-y-3">
            <Label htmlFor="narrative-font" className="font-mono text-sm">
              Narrative Text
            </Label>
            <Select value={fonts.narrativeFont} onValueChange={setNarrativeFont}>
              <SelectTrigger id="narrative-font" className="font-mono">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {NARRATIVE_FONTS.map((font) => (
                  <SelectItem key={font} value={font} className="font-mono">
                    <span style={{ fontFamily: font }}>{font}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground font-mono">
              Font used for story content and narrative text
            </p>
          </div>

          {/* UI Text Font */}
          <div className="space-y-3">
            <Label htmlFor="ui-font" className="font-mono text-sm">
              UI Text
            </Label>
            <Select value={fonts.uiFont} onValueChange={setUIFont}>
              <SelectTrigger id="ui-font" className="font-mono">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UI_FONTS.map((font) => (
                  <SelectItem key={font} value={font} className="font-mono">
                    <span style={{ fontFamily: font }}>{font}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground font-mono">
              Fixed-width font for buttons, labels, and interface elements
            </p>
          </div>

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
                  className={`text-xs font-mono ${
                    uploadMessage.type === 'success' ? 'text-green-600' : 'text-destructive'
                  }`}
                >
                  {uploadMessage.text}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Preview Section */}
      <Card>
        <CardHeader>
          <CardTitle className="font-mono">Preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="font-mono text-sm mb-2 block">Narrative Text Sample:</Label>
            <div
              className="p-4 rounded-md bg-muted/50 text-sm leading-relaxed"
              style={{ fontFamily: fonts.narrativeFont }}
            >
              The rain hammered against the neon-lit windows of the megastructure. In the distance,
              chrome towers pierced the smog-choked sky. This was the world they'd inherited - a
              tapestry of silicon dreams and broken promises.
            </div>
          </div>
          <div>
            <Label className="font-mono text-sm mb-2 block">UI Text Sample:</Label>
            <div className="space-y-2">
              <Button variant="outline" style={{ fontFamily: fonts.uiFont }}>
                Sample Button
              </Button>
              <p className="text-sm text-muted-foreground" style={{ fontFamily: fonts.uiFont }}>
                Menu items and labels appear in this font
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
      </div>
    </ScrollArea>
  );
}
