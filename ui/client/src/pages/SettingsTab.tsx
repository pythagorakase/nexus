/**
 * Settings page for customizing font preferences.
 */
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

  return (
    <div className="container max-w-4xl py-8 space-y-6">
      <div>
        <h2 className="text-2xl font-mono font-bold mb-2">Settings</h2>
        <p className="text-muted-foreground font-mono text-sm">
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
  );
}
