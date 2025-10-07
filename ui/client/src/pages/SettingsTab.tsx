/**
 * Settings page for customizing font preferences and PWA icon.
 */
import { useState } from 'react';
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
import { Loader2, Upload, Image as ImageIcon } from 'lucide-react';

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
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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
              chrome towers pierced the smog-choked sky. This was the world they'd inherited—a
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
