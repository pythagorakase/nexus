/** Real components and seeded query data: no server, store, inference or action mocks. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { TopBar } from '@/components/nexus/TopBar';
import { LocalModelRows } from '@/components/nexus/LocalModelRows';
// The build exports the existing private renderer from its source, without a product edit.
import { KeyStatusGlyph, SettingsCard } from '@/components/nexus/SettingsPane';
import { MapPane } from '@/components/nexus/MapPane';
const knobs = { poll_idle_ms: 1e8, poll_busy_ms: 1e8, download_poll_ms: 1e8, delete_arm_ms: 600 };
const places = [1, 2, 3, 4].map(id => ({ id, name: `Place ${id}`, type: 'fixed_location', zone: 1,
  geometry: { type: 'Point', coordinates: [id % 2 ? 0 : 10, id < 3 ? 0 : 5] }, coordinates: null, geom: null }));
function cache(theme: string, active = false, exceeds = false) {
  const c = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, gcTime: Infinity, retry: false } } });
  c.setQueryData(['/api/local-models/status'], { models_dir: '/models', system_ram_gb: 32,
    catalog: [{ family: 'fixture', label: 'Fixture Q4', hf_repo: 'fixture', subdir: 'fixture', filename: 'model.gguf', quant: 'Q4', size_gb: exceeds ? 50 : 16, min_ram_gb: exceeds ? 96 : 16 }],
    installed: [{ path: '/models/fixture/model.gguf', filename: 'model.gguf', arch: 'fixture', quant: 'Q4', size_bytes: exceeds ? 50e9 : 16e9, verified: true, active: false }],
    active: active ? { gguf_path: '/models/fixture/model.gguf', ready: true, failed: false } : null });
  c.setQueryData(['/api/local-models/download'], { state: 'idle' });
  c.setQueryData(['/api/settings'], { ui: { local_models: knobs, theme } });
  c.setQueryData(['/api/preferences'], { ui: { theme } });
  c.setQueryData(['/api/places', 4], places);
  c.setQueryData(['/api/zones', 4], [{ id: 1, name: 'Fixture', summary: null, boundary: null }]);
  c.setQueryData(['/api/current-place', 4], [{ placeId: 4, name: 'Place 4', chunkId: 1 }]);
  for (const p of places) c.setQueryData(['/api/places', p.id, 'images', 4], []);
  return c;
}
const root = createRoot(document.getElementById('root')!);
(window as any).renderSurfaces = (theme: string) => {
  document.documentElement.className = `dark theme-${theme}`;
  root.render(<div key={theme} className="nexus-shell"><div data-memory="normal"><QueryClientProvider client={cache(theme, true)}><TopBar slot={4} characterName={null} skaldStatus="READY" failedGeneration={null} frontierClock={null}/></QueryClientProvider></div>
    <div data-memory="over"><QueryClientProvider client={cache(theme, true, true)}><TopBar slot={4} characterName={null} skaldStatus="READY" failedGeneration={null} frontierClock={null}/></QueryClientProvider></div>
    <div className="nexus-main no-ledger"><aside className="left-rail"/><main className="nexus-content"><div className="settings-pane-v2"><div className="set-scroller">
      <SettingsCard id="model" label="MODEL"><ul className="model-providers">{[false, true].map(exceeds => <li key={String(exceeds)} className="model-provider open" data-delete={exceeds ? 'ready-exceeds' : 'ready'}><ul className="model-list"><QueryClientProvider client={cache(theme, false, exceeds)}><LocalModelRows selected={false} onPickLocal={() => {}} knobs={knobs}/></QueryClientProvider></ul></li>)}</ul></SettingsCard>
      <SettingsCard id="keys" label="API KEYS"><ul className="key-list">{['required', 'optional'].flatMap(need => ['optional-absent', 'required-missing', 'present', 'verified'].map(state => {
        const required = state === 'required-missing' || (need === 'required' && state !== 'optional-absent');
        const present = state === 'present' || state === 'verified';
        const verified = state === 'verified';
        const status = verified ? 'verified' : present ? 'present' : 'absent';
        return <li key={`${need}/${state}`} data-key={`${need}/${state}`} className={`key-row ${!required ? 'optional' : present ? 'required' : 'required missing'}`}><span className="key-provider-name">{state}</span><span className={`key-status ${status}`}><KeyStatusGlyph required={required} present={present} verified={verified}/></span><input className="key-input" aria-label={`${need}/${state}`}/></li>;
      }))}</ul></SettingsCard>
    </div></div></main></div><div className="nexus-main no-ledger"><aside className="left-rail"/><main className="nexus-content"><QueryClientProvider client={cache(theme)}><ThemeProvider><MapPane slot={4}/></ThemeProvider></QueryClientProvider></main></div>
  </div>);
};
