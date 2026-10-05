/** Production shell and sections with immutable, in-page synthetic data. */
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal, flushSync } from 'react-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { DeveloperModeProvider } from '@/contexts/DeveloperModeContext';
import { NexusLayout } from '@/components/nexus/NexusLayout';
import { MapPane } from '@/components/nexus/MapPane';
// Exported at bundle time, without editing the production module.
import { ModelSection, KeysSection, SectionRail } from '@/components/nexus/SettingsPane';
import { LOCAL_PROVIDER } from '@/components/nexus/LocalModelRows';
import { secretsQueryKey } from '@/hooks/useSecrets';

localStorage.removeItem('activeSlot');
const replace = history.replaceState.bind(history);
history.replaceState = (data, unused, url) => replace(data, unused,
  new URL(`?tab=${new URL(String(url), 'http://fixture').searchParams.get('tab') ?? 'narrative'}`, location.href));
const knobs = { poll_idle_ms: 1e8, poll_busy_ms: 1e8, download_poll_ms: 1e8, delete_arm_ms: 60000 };
let currentClient: QueryClient;
let keyRows: any[] = [];
(window as any).fixtureTransport = [];
// Only fixture records are served; no request leaves the browser and no key/store is consulted.
window.fetch = async (input, init) => {
  const url = String(input), method = init?.method ?? 'GET';
  (window as any).fixtureTransport.push({ method, url });
  if (method === 'GET' && url === '/api/secrets/status?slot=4') return Response.json(keyRows);
  if (method === 'POST' && /^\/api\/secrets\/verified\/verify$/.test(url))
    return Response.json({ provider: 'verified', verified: true, detail: 'synthetic fixture revision' });
  throw new Error(`Unexpected fixture request: ${method} ${url}`);
};
const status = (active = false, over = false) => ({ models_dir: '/models', system_ram_gb: 32,
  catalog: [{ family: 'fixture', label: 'Fixture Q4', hf_repo: 'fixture', subdir: 'fixture', filename: 'model.gguf', quant: 'Q4', size_gb: over ? 50 : 16, min_ram_gb: over ? 96 : 16 }],
  installed: [{ path: '/models/fixture/model.gguf', filename: 'model.gguf', arch: 'fixture', quant: 'Q4', size_bytes: over ? 50e9 : 16e9, verified: true, active: false }],
  active: active ? { gguf_path: '/models/fixture/model.gguf', ready: true, failed: false } : null });
function cache(theme: string, mode: string, terrain: string, over: boolean, need: string) {
  const c = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, gcTime: Infinity, retry: false, refetchOnWindowFocus: false } } });
  const settings = { ui: { theme, local_models: knobs }, local_models: { model: 'fixture-local' }, apex: { model: 'fixture-other' },
    settings_meta: { models: [{ id: 'fixture-local', provider: LOCAL_PROVIDER, label: 'Fixture' }], apex_allowed_providers: [LOCAL_PROVIDER] } };
  c.setQueryData(['/api/settings'], settings);
  c.setQueryData(['/api/preferences'], { theme });
  c.setQueryData(['/api/dev/backstage/health'], false);
  c.setQueryData(['/api/local-models/status'], status(mode === 'memory', over));
  c.setQueryData(['/api/local-models/download'], { state: 'idle' });
  const [lng, lat] = terrain === 'land' ? [-100, 40] : [-30, 0];
  const places = [1, 2, 3, 4].map(id => ({ id, name: `Place ${id}`, type: 'fixed_location', zone: 1,
    geometry: { type: 'Point', coordinates: [lng + (id % 2 ? 0 : .05), lat + (id < 3 ? 0 : .05)] }, coordinates: null, geom: null }));
  c.setQueryData(['/api/places', 4], places);
  c.setQueryData(['/api/zones', 4], [{ id: 1, name: 'Fixture', summary: null, boundary: null }]);
  c.setQueryData(['/api/current-place', 4], [{ placeId: 4, name: 'Place 4', chunkId: 1 }]);
  for (const p of places) c.setQueryData(['/api/places', p.id, 'images', 4], []);
  keyRows = ['optional-absent', 'required-missing', 'present', 'verified'].map(state => ({ provider: state, account: 'fixture',
    required: state === 'required-missing' || (need === 'required' && state !== 'optional-absent'),
    present: state === 'present' || state === 'verified', last4: null, required_by: [] }));
  c.setQueryData(secretsQueryKey(4), keyRows);
  return { c, settings };
}
function Fixture({ mode, settings }: { mode: string; settings: any }) {
  const [host, setHost] = useState<Element | null>(null);
  useEffect(() => { const main = document.querySelector('.nexus-content')!;
    main.querySelector('.pane-notice')?.remove(); setHost(main); }, []);
  return <><NexusLayout />{host && mode !== 'memory' && createPortal(mode === 'map' ? <MapPane slot={4} /> :
    <div className="settings-pane-v2"><SectionRail active={mode === 'delete' ? 'model' : 'keys'} onPick={() => {}}
      sections={[{ id: 'model', label: 'Model' }, { id: 'keys', label: 'API Keys' }]} />
      <div className="set-scroller">{mode === 'delete' ? <ModelSection settings={settings} onPickSkald={() => {}} onPickGaia={() => {}} /> : <KeysSection slot={4} />}</div>
    </div>, host)}</>;
}
let revision = 0;
const root = createRoot(document.getElementById('root')!);
(window as any).renderSurfaces = (theme: string, mode: string, terrain = 'sea', over = false, need = 'required') => {
  const { c, settings } = cache(theme, mode, terrain, over, need); currentClient?.clear(); currentClient = c;
  localStorage.setItem('nexus-theme', theme);
  flushSync(() => root.render(<QueryClientProvider key={`${++revision}/${theme}/${mode}/${terrain}/${over}/${need}`} client={c}><ThemeProvider><DeveloperModeProvider>
    <Fixture mode={mode} settings={settings} />
  </DeveloperModeProvider></ThemeProvider></QueryClientProvider>));
};
(window as any).setOver = (over: boolean) => currentClient.setQueryData(['/api/local-models/status'], status(true, over));
