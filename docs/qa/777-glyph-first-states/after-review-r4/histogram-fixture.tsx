import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {ThemeProvider} from '@/contexts/ThemeContext';
import {DeveloperModeProvider} from '@/contexts/DeveloperModeContext';
import {NexusLayout} from '@/components/nexus/NexusLayout';
import {MapPane} from '@/components/nexus/MapPane';
localStorage.removeItem('activeSlot');
// Preserve file:// transport while the actual shell updates its tab URL.
const replace = history.replaceState.bind(history);
history.replaceState = (data, unused, url) => replace(data, unused, new URL(`?tab=${new URL(String(url), 'http://fixture').searchParams.get('tab') ?? 'narrative'}`, location.href));
const c = new QueryClient({defaultOptions:{queries:{staleTime:Infinity,gcTime:Infinity,retry:false}}});
const status = (over = false) => ({models_dir:'/models',system_ram_gb:32,catalog:[], installed:[{path:'/model.gguf',filename:'model.gguf',arch:'fixture',quant:'Q4',size_bytes:over ? 50e9 : 16e9,verified:true,active:true}],active:{gguf_path:'/model.gguf',ready:true,failed:false}});
c.setQueryData(['/api/local-models/status'],status());
c.setQueryData(['/api/settings'],{ui:{theme:'veil',local_models:{poll_idle_ms:1e8,poll_busy_ms:1e8}}});
c.setQueryData(['/api/preferences'],{theme:'veil'});
c.setQueryData(['/api/dev/backstage/health'],false);
const places=[1,2,3,4].map(id=>({id,name:`Place ${id}`,type:'fixed_location',zone:1,geometry:{type:'Point',coordinates:[id%2?0:.05,id<3?0:.05]},coordinates:null,geom:null}));
c.setQueryData(['/api/places',4],places);
c.setQueryData(['/api/zones',4],[{id:1,name:'Fixture',summary:null,boundary:null}]);
c.setQueryData(['/api/current-place',4],[{placeId:4,name:'Place 4',chunkId:1}]);
function Fixture(){const [host,setHost]=useState<Element|null>(null); useEffect(()=>setHost(document.querySelector('.nexus-content')),[]);return <><NexusLayout/>{host&&createPortal(<MapPane slot={4}/>,host)}</>}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={c}><ThemeProvider><DeveloperModeProvider><Fixture/></DeveloperModeProvider></ThemeProvider></QueryClientProvider>);
(window as any).setOver = (over:boolean)=>c.setQueryData(['/api/local-models/status'],status(over));
