/** 777-KBD proof fixture: a copy of ui/scripts/state-surfaces/fixture.tsx (production shell, immutable in-page synthetic data) with a seven-member cast and a Garden Rings zone added. fixture.tsx itself is untouched. */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FontProvider, KEEPERS } from '@/contexts/FontContext';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { DeveloperModeProvider } from '@/contexts/DeveloperModeContext';
import { NexusLayout } from '@/components/nexus/NexusLayout';
import { LOCAL_PROVIDER } from '@/components/nexus/LocalModelRows';
import { UI_CONFIG_KEY } from '@/hooks/useUiConfig';
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
  if (method === 'HEAD' && url === '/api/settings') return new Response(null);
  if (method === 'GET' && url === '/api/narrative/active?slot=4') return Response.json(null);
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
  const settings = { ui: { theme, local_models: knobs, fonts: KEEPERS }, local_models: { model: 'fixture-local' }, apex: { model: 'fixture-other' },
    settings_meta: { models: [{ id: 'fixture-local', provider: LOCAL_PROVIDER, label: 'Fixture' }], apex_allowed_providers: [LOCAL_PROVIDER] } };
  c.setQueryData(['/api/settings'], settings);
  c.setQueryData(UI_CONFIG_KEY, { announcer: { hold_ms: 5000 } });
  c.setQueryData(['/api/slot/4/settings'], { skald_model: 'fixture-other', gaia_model: null, apex_context_window: 8192 });
  c.setQueryData(['/api/user-character', 4], null);
  const generation = { poll_interval_seconds: 1e8, request_timeout_seconds: 10 };
  c.setQueryData(['/api/slot/state', 4], { narrative_generation: generation, frontier_clock: null });
  c.setQueryData(['/api/preferences', 'narrative-recovery'], { narrative_generation: generation });
  c.setQueryData(['/api/preferences'], { theme });
  c.setQueryData(['/api/dev/backstage/health'], false);
  c.setQueryData(['/api/local-models/status'], status(mode === 'memory', over));
  c.setQueryData(['/api/local-models/download'], { state: 'idle' });
  const [lng, lat] = terrain === 'land' ? [-100, 40] : [-30, 0];
  const placeNames = ['Ring One Hydroponics', 'Ring Two Market', 'Ring Three Public Kitchen', 'Spindle Dock'];
  const places = [1, 2, 3, 4].map(id => ({ id, name: placeNames[id - 1], type: 'fixed_location', zone: 1,
    summary: id === 3 ? 'Long tables under grow lamps; the ring eats here.' : null,
    geometry: { type: 'Point', coordinates: [lng + (id % 2 ? 0 : .05), lat + (id < 3 ? 0 : .05)] }, coordinates: null, geom: null }));
  c.setQueryData(['/api/places', 4], places);
  c.setQueryData(['/api/zones', 4], [{ id: 1, name: 'Accord Station Garden Rings', summary: null, boundary: null }]);
  const cast = ['Ivo Sato', 'Pela', 'Mara Quill', 'Tobias Fenn', 'Rhea Lind', 'Osei Vance', 'Juno Halloran'].map((name, index) => ({
    id: index + 1, name, summary: `${name} keeps a post on the station.`, appearance: null, background: null, personality: null,
    emotionalState: null, currentActivity: null, currentLocation: null, extraData: null,
    createdAt: '2026-10-01T00:00:00Z', updatedAt: '2026-10-01T00:00:00Z', currentLocationName: null, portraitPath: null }));
  c.setQueryData(['/api/characters', 4], cast);
  for (const member of cast) c.setQueryData(['/api/characters/images', member.id, 4], []);
  c.setQueryData(['/api/current-place', 4], [{ placeId: 4, name: placeNames[3], chunkId: 1 }]);
  for (const p of places) c.setQueryData(['/api/places', p.id, 'images', 4], []);
  keyRows = ['optional-absent', 'required-missing', 'present', 'verified'].map(state => ({ provider: state, account: 'fixture',
    required: state === 'required-missing' || (need === 'required' && state !== 'optional-absent'),
    present: state === 'present' || state === 'verified', last4: null, required_by: [] }));
  c.setQueryData(secretsQueryKey(4), keyRows);
  return { c, settings };
}
let revision = 0;
const root = createRoot(document.getElementById('root')!);
(window as any).renderSurfaces = (theme: string, mode: string, terrain = 'sea', over = false, need = 'required') => {
  const { c, settings } = cache(theme, mode, terrain, over, need); currentClient?.clear(); currentClient = c;
  localStorage.setItem('nexus-theme', theme);
  if (mode === 'memory') localStorage.removeItem('activeSlot');
  else localStorage.setItem('activeSlot', '4');
  history.replaceState(null, '', `?tab=${mode === 'map' ? 'map' : mode === 'characters' ? 'characters' : mode === 'memory' ? 'narrative' : 'settings'}`);
  flushSync(() => root.render(<QueryClientProvider key={`${++revision}/${theme}/${mode}/${terrain}/${over}/${need}`} client={c}><ThemeProvider><DeveloperModeProvider>
    <FontProvider><TooltipProvider><NexusLayout /></TooltipProvider></FontProvider>
  </DeveloperModeProvider></ThemeProvider></QueryClientProvider>));
};
(window as any).setOver = (over: boolean) => currentClient.setQueryData(['/api/local-models/status'], status(true, over));
