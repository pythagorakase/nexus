# Complete Before/After Pair Measurements

## Veil

Joint maximum minimum ΔE: **9.913464335675082**. Exhaustive full-domain count: **258280326000000**; satisfying assignments: **0**; changed roots at the selected tie-break: **5**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--state-mem-normal` | `hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)` |
| `--state-mem-over` | `hsl(15 75% 60%)` |
| `--state-delete-unarmed` | `hsl(42 30% 65%)` |
| `--state-delete-armed` | `hsl(0 80% 50%)` |
| `--state-map-rest` | `hsl(15 75% 60%)` |
| `--state-map-current` | `hsl(330.2439024390244 70% 50%)` |
| `--state-map-selected` | `hsl(330.2439024390244 50.20408163265306% 70%)` |
| `--state-map-hovered` | `hsl(330.2439024390244 60% 30%)` |
| `--state-key-absent` | `hsl(42 20% 50%)` |
| `--state-key-missing` | `hsl(15 75% 60%)` |
| `--state-key-present` | `hsl(42 50% 70%)` |
| `--state-key-verified` | `hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (189.720,55.080,144.840); (229.500,114.750,76.500) | (184.000,61.000,122.000); (229.500,114.750,76.500) | 38.002783748871494 | 28.68503954807601 |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (192.525,176.460,138.975); (210.375,44.625,44.625) | (192.525,176.460,138.975); (229.500,25.500,25.500) | 20.80376452918997 | 20.37987230073326 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (73.351,70.380,62.564); (79.598,24.238,29.542) | (73.351,70.380,62.564); (86.292,17.544,22.848) | 9.51238876756636 | 11.405805656799993 † |
| key: optional-absent / required-missing | required/rest, optional/rest | (81.090,75.480,61.710); (229.500,114.750,76.500) | (81.090,75.480,61.710); (229.500,114.750,76.500) | 35.826832286531086 | 35.826832286531086 |
| key: optional-absent / present | required/rest | (81.090,75.480,61.710); (192.525,176.460,138.975) | (81.090,75.480,61.710); (216.750,193.800,140.250) | 40.38140915874647 | 45.50260432163349 |
| key: optional-absent / verified | required/rest | (81.090,75.480,61.710); (189.720,55.080,144.840) | (81.090,75.480,61.710); (184.000,61.000,122.000) | 24.91703362959893 | 17.471028667646113 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (229.500,114.750,76.500); (192.525,176.460,138.975) | (229.500,114.750,76.500); (216.750,193.800,140.250) | 11.447234141252315 | 12.729354582154402 † |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (184.000,61.000,122.000) | 38.002783748871494 | 28.68503954807601 |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (192.525,176.460,138.975); (189.720,55.080,144.840) | (216.750,193.800,140.250); (184.000,61.000,122.000) | 33.74473623257419 | 32.83734573473908 |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (229.500,114.750,76.500) | (153.000,137.700,102.000); (229.500,114.750,76.500) | 10.828932806147856 | 10.828932806147856 † |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (192.525,176.460,138.975) | (153.000,137.700,102.000); (216.750,193.800,140.250) | 11.904163763235427 | 17.25307756237176 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (189.720,55.080,144.840) | (153.000,137.700,102.000); (184.000,61.000,122.000) | 28.357466144039577 | 19.174033902176223 |
| key: optional-absent / present | optional/rest | (81.090,75.480,61.710); (100.853,94.860,80.198) | (81.090,75.480,61.710); (112.965,103.530,80.835) | 6.861207612606855 | 10.87802426264397 † |
| key: optional-absent / verified | optional/rest | (81.090,75.480,61.710); (99.450,34.170,83.130) | (81.090,75.480,61.710); (96.590,37.130,71.710) | 18.76076985549963 | 13.741295960893453 † |
| key: required-missing / present | optional/rest | (229.500,114.750,76.500); (100.853,94.860,80.198) | (229.500,114.750,76.500); (112.965,103.530,80.835) | 28.46237996653055 | 23.29328104810856 |
| key: required-missing / verified | optional/rest | (229.500,114.750,76.500); (99.450,34.170,83.130) | (229.500,114.750,76.500); (96.590,37.130,71.710) | 49.861998154488546 | 46.28426679252508 |
| key: present / verified | optional/rest | (100.853,94.860,80.198); (99.450,34.170,83.130) | (112.965,103.530,80.835); (96.590,37.130,71.710) | 21.55216217024095 | 22.19949279768684 |
| map: rest / current | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (216.750,38.250,126.774) | 36.519036034009964 | 22.33679994607939 |
| map: rest / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (216.906,140.094,178.188) | 38.002783748871494 | 27.922641521946684 |
| map: rest / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (122.400,30.600,76.127) | 36.519036034009964 | 40.238029984278675 |
| map: current / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (214.200,91.800,173.400); (189.720,55.080,144.840) | (216.750,38.250,126.774); (216.906,140.094,178.188) | 9.571575278395933 | 15.084204044785425 |
| map: current / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (214.200,91.800,173.400); (214.200,91.800,173.400) | (216.750,38.250,126.774); (122.400,30.600,76.127) | 0 | 20.787398019833503 |
| map: selected / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (189.720,55.080,144.840); (214.200,91.800,173.400) | (216.906,140.094,178.188); (122.400,30.600,76.127) | 9.571575278395933 | 37.90851200860483 |
| map: rest / current | canvas-sea/ring | (229.500,114.750,76.500); (131.580,59.500,111.180) | (229.500,114.750,76.500); (133.110,27.370,83.205) | 43.28622726344373 | 39.43184719311035 |
| map: rest / selected | canvas-sea/ring | (229.500,114.750,76.500); (116.892,37.468,94.044) | (229.500,114.750,76.500); (133.204,88.476,114.053) | 47.47355255794096 | 34.21722891708048 |
| map: rest / hovered | canvas-sea/ring | (229.500,114.750,76.500); (131.580,59.500,111.180) | (229.500,114.750,76.500); (76.500,22.780,52.816) | 43.28622726344373 | 48.996593369389224 |
| map: current / selected | canvas-sea/ring | (131.580,59.500,111.180); (116.892,37.468,94.044) | (133.110,27.370,83.205); (133.204,88.476,114.053) | 5.619200746846419 | 9.913464335675082 † |
| map: current / hovered | canvas-sea/ring | (131.580,59.500,111.180); (131.580,59.500,111.180) | (133.110,27.370,83.205); (76.500,22.780,52.816) | 0 | 10.749294590590697 † |
| map: selected / hovered | canvas-sea/ring | (116.892,37.468,94.044); (131.580,59.500,111.180) | (133.204,88.476,114.053); (76.500,22.780,52.816) | 5.619200746846419 | 19.874575983092274 |
| map: rest / current | canvas-land/ring | (229.500,114.750,76.500); (143.232,62.318,119.307) | (229.500,114.750,76.500); (144.396,30.567,89.870) | 41.67385657003848 | 36.84358226984748 |
| map: rest / selected | canvas-land/ring | (229.500,114.750,76.500); (128.544,40.286,102.171) | (229.500,114.750,76.500); (144.490,91.673,120.718) | 45.82269295419665 | 32.69117033440439 |
| map: rest / hovered | canvas-land/ring | (229.500,114.750,76.500); (143.232,62.318,119.307) | (229.500,114.750,76.500); (87.786,25.977,59.482) | 41.67385657003848 | 47.08558551657648 |
| map: current / selected | canvas-land/ring | (143.232,62.318,119.307); (128.544,40.286,102.171) | (144.396,30.567,89.870); (144.490,91.673,120.718) | 5.687471528003299 | 10.051865594318292 † |
| map: current / hovered | canvas-land/ring | (143.232,62.318,119.307); (143.232,62.318,119.307) | (144.396,30.567,89.870); (87.786,25.977,59.482) | 0 | 10.96304820174595 † |
| map: selected / hovered | canvas-land/ring | (128.544,40.286,102.171); (143.232,62.318,119.307) | (144.490,91.673,120.718); (87.786,25.977,59.482) | 5.687471528003299 | 20.12041898256543 |
| map: rest / current | sidebar-wash-0/rest/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (133.722,28.254,84.633) | 36.519036034009964 | 39.644015852397146 |
| map: rest / selected | sidebar-wash-0/rest/ring, sidebar-wash-0/hover/ring, sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (142.207,91.652,120.308) | 38.002783748871494 | 33.181661889093924 |
| map: rest / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (77.112,23.664,54.244) | 36.519036034009964 | 49.13640338458866 |
| map: current / selected | sidebar-wash-0/rest/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (133.722,28.254,84.633); (142.207,91.652,120.308) | 9.571575278395933 | 11.666006604400076 † |
| map: current / hovered | sidebar-wash-0/rest/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (133.722,28.254,84.633); (77.112,23.664,54.244) | 0 | 10.72837175025363 † |
| map: selected / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (142.207,91.652,120.308); (77.112,23.664,54.244) | 9.571575278395933 | 21.704037881126453 |
| map: rest / current | sidebar-wash-0/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (140.046,31.722,90.549) | 36.519036034009964 | 38.881487440614336 |
| map: rest / hovered | sidebar-wash-0/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (83.436,27.132,60.160) | 36.519036034009964 | 48.51688796069563 |
| map: current / selected | sidebar-wash-0/hover/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (140.046,31.722,90.549); (142.207,91.652,120.308) | 9.571575278395933 | 9.984786986254417 † |
| map: current / hovered | sidebar-wash-0/hover/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (140.046,31.722,90.549); (83.436,27.132,60.160) | 0 | 10.77898032697899 † |
| map: selected / hovered | sidebar-wash-0/hover/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (142.207,91.652,120.308); (83.436,27.132,60.160) | 9.571575278395933 | 20.2425609889429 |
| map: rest / current | sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (142.113,30.546,89.460) | 36.519036034009964 | 37.70226814703448 |
| map: current / selected | sidebar-wash-0/selected-current/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (142.113,30.546,89.460); (142.207,91.652,120.308) | 9.571575278395933 | 10.03693437831006 † |
| map: current / hovered | sidebar-wash-0/selected-current/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (142.113,30.546,89.460); (77.112,23.664,54.244) | 0 | 12.564460481018687 † |
| map: rest / current | sidebar-wash-0.07/rest/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (137.892,29.168,87.412) | 36.519036034009964 | 38.90213217218864 |
| map: rest / selected | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/hover/ring, sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (145.876,92.456,122.755) | 38.002783748871494 | 32.94051626834592 |
| map: rest / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (81.282,24.578,57.024) | 36.519036034009964 | 48.61053676077338 |
| map: current / selected | sidebar-wash-0.07/rest/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (137.892,29.168,87.412); (145.876,92.456,122.755) | 9.571575278395933 | 11.586832012650982 † |
| map: current / hovered | sidebar-wash-0.07/rest/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (137.892,29.168,87.412); (81.282,24.578,57.024) | 0 | 10.817263676958488 † |
| map: selected / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (145.876,92.456,122.755); (81.282,24.578,57.024) | 9.571575278395933 | 21.682549454144063 |
| map: rest / current | sidebar-wash-0.07/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (142.131,32.179,91.939) | 36.519036034009964 | 38.495877930153505 |
| map: rest / hovered | sidebar-wash-0.07/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (85.521,27.589,61.550) | 36.519036034009964 | 48.25647853520175 |
| map: current / selected | sidebar-wash-0.07/hover/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (142.131,32.179,91.939); (145.876,92.456,122.755) | 9.571575278395933 | 10.335348887008438 † |
| map: current / hovered | sidebar-wash-0.07/hover/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (142.131,32.179,91.939); (85.521,27.589,61.550) | 0 | 10.827111892377111 † |
| map: selected / hovered | sidebar-wash-0.07/hover/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (145.876,92.456,122.755); (85.521,27.589,61.550) | 9.571575278395933 | 20.609099728268944 |
| map: rest / current | sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (145.783,31.350,91.907) | 36.519036034009964 | 37.00186819136731 |
| map: current / selected | sidebar-wash-0.07/selected-current/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (145.783,31.350,91.907); (145.876,92.456,122.755) | 9.571575278395933 | 10.057659569248456 † |
| map: current / hovered | sidebar-wash-0.07/selected-current/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (145.783,31.350,91.907); (81.282,24.578,57.024) | 0 | 12.563126639381546 † |

All individual pair/context maxima and maximizing witnesses are in `veil-joint.json`. Each individual maximum exhausts the two independent state domains; count and witnesses are reported explicitly. They provide context and do not determine joint-exception acceptance. Full-domain coverage exhausts each surface factor and combines all twelve independent state domains exactly.

## Gilded

Joint maximum minimum ΔE: **11.515866170801722**. Exhaustive full-domain count: **446308403328000**; satisfying assignments: **0**; changed roots at the selected tie-break: **8**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--state-mem-normal` | `hsl(43 74% 47%)` |
| `--state-mem-over` | `hsl(30 50% 45%)` |
| `--state-delete-unarmed` | `hsl(43 40% 70%)` |
| `--state-delete-armed` | `hsl(0 90% 50%)` |
| `--state-map-rest` | `hsl(30 50% 70%)` |
| `--state-map-current` | `hsl(45 75% 40%)` |
| `--state-map-selected` | `hsl(43 84% 60%)` |
| `--state-map-hovered` | `hsl(45 55% 30%)` |
| `--state-key-absent` | `hsl(43 30% 30%)` |
| `--state-key-missing` | `hsl(30 50% 45%)` |
| `--state-key-present` | `hsl(43 40% 70%)` |
| `--state-key-verified` | `hsl(43 74% 47%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (208.539,158.282,31.161); (172.125,114.750,57.375) | (208.539,158.282,31.161); (172.125,114.750,57.375) | 14.337990382173535 | 14.337990382173535 † |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (181.560,153.816,83.640); (195.075,34.425,34.425) | (209.100,191.760,147.900); (242.250,12.750,12.750) | 17.039081906673687 | 21.29062847998195 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (70.176,60.466,35.904); (74.906,18.679,18.679) | (79.815,73.746,58.395); (91.417,11.092,11.092) | 6.273849550380767 | 12.037121999967614 † |
| key: optional-absent / required-missing | required/rest, optional/rest | (71.400,62.730,40.800); (172.125,114.750,57.375) | (54.825,48.322,31.875); (172.125,114.750,57.375) | 27.558605649270802 | 32.49244138885215 |
| key: optional-absent / present | required/rest | (71.400,62.730,40.800); (181.560,153.816,83.640) | (54.825,48.322,31.875); (209.100,191.760,147.900) | 38.88438534602612 | 58.56181365418784 |
| key: optional-absent / verified | required/rest | (71.400,62.730,40.800); (208.539,158.282,31.161) | (54.825,48.322,31.875); (208.539,158.282,31.161) | 45.991602192291126 | 50.79335425394908 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (181.560,153.816,83.640) | (172.125,114.750,57.375); (209.100,191.760,147.900) | 9.20305994887555 | 20.063656851921923 |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (208.539,158.282,31.161) | (172.125,114.750,57.375); (208.539,158.282,31.161) | 14.337990382173535 | 14.337990382173535 † |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (181.560,153.816,83.640); (208.539,158.282,31.161) | (209.100,191.760,147.900); (208.539,158.282,31.161) | 8.084904016113446 | 14.889609692629227 † |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (172.125,114.750,57.375) | (99.450,86.445,53.550); (172.125,114.750,57.375) | 7.72892192098335 | 18.784598711480943 |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (181.560,153.816,83.640) | (99.450,86.445,53.550); (209.100,191.760,147.900) | 15.32055288939221 | 36.941089895489256 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (208.539,158.282,31.161) | (99.450,86.445,53.550); (208.539,158.282,31.161) | 21.598012943420677 | 34.346574359376135 |
| key: optional-absent / present | optional/rest | (71.400,62.730,40.800); (95.880,82.008,46.920) | (54.825,48.322,31.875); (109.650,100.980,79.050) | 8.110992474373157 | 18.12584341746114 |
| key: optional-absent / verified | optional/rest | (71.400,62.730,40.800); (109.370,84.241,20.680) | (54.825,48.322,31.875); (109.370,84.241,20.680) | 13.774703240065797 | 18.465987459750902 |
| key: required-missing / present | optional/rest | (172.125,114.750,57.375); (95.880,82.008,46.920) | (172.125,114.750,57.375); (109.650,100.980,79.050) | 19.807242349119495 | 16.98801900564459 |
| key: required-missing / verified | optional/rest | (172.125,114.750,57.375); (109.370,84.241,20.680) | (172.125,114.750,57.375); (109.370,84.241,20.680) | 16.41371532037838 | 16.41371532037838 |
| key: present / verified | optional/rest | (95.880,82.008,46.920); (109.370,84.241,20.680) | (109.650,100.980,79.050); (109.370,84.241,20.680) | 6.779403334981554 | 12.046424121385503 † |
| map: rest / current | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (178.500,140.250,25.500) | 16.800428551875378 | 16.14720424122858 |
| map: rest / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (208.539,158.282,31.161) | (216.750,178.500,140.250); (238.680,190.128,67.320) | 14.337990382173535 | 13.210556095722884 † |
| map: rest / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (118.575,97.538,34.425) | 16.800428551875378 | 29.753934163514682 |
| map: current / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (209.100,181.050,96.900); (208.539,158.282,31.161) | (178.500,140.250,25.500); (238.680,190.128,67.320) | 6.961704626353169 | 14.830663743646534 † |
| map: current / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (209.100,181.050,96.900); (209.100,181.050,96.900) | (178.500,140.250,25.500); (118.575,97.538,34.425) | 0 | 19.482975840946782 |
| map: selected / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (208.539,158.282,31.161); (209.100,181.050,96.900) | (238.680,190.128,67.320); (118.575,97.538,34.425) | 6.961704626353169 | 33.483560259956604 |
| map: rest / current | canvas-sea/ring | (172.125,114.750,57.375); (130.560,113.730,63.240) | (216.750,178.500,140.250); (112.200,89.250,20.400) | 7.326844090326136 | 33.323236491428375 |
| map: rest / selected | canvas-sea/ring | (172.125,114.750,57.375); (130.223,100.069,23.797) | (216.750,178.500,140.250); (148.308,119.177,45.492) | 9.862954046610353 | 20.757427595625877 |
| map: rest / hovered | canvas-sea/ring | (172.125,114.750,57.375); (130.560,113.730,63.240) | (216.750,178.500,140.250); (76.245,63.623,25.755) | 7.326844090326136 | 47.7205412164042 |
| map: current / selected | canvas-sea/ring | (130.560,113.730,63.240); (130.223,100.069,23.797) | (112.200,89.250,20.400); (148.308,119.177,45.492) | 6.3659257084362935 | 12.294267210601289 † |
| map: current / hovered | canvas-sea/ring | (130.560,113.730,63.240); (130.560,113.730,63.240) | (112.200,89.250,20.400); (76.245,63.623,25.755) | 0 | 11.560012951813665 † |
| map: selected / hovered | canvas-sea/ring | (130.223,100.069,23.797); (130.560,113.730,63.240) | (148.308,119.177,45.492); (76.245,63.623,25.755) | 6.3659257084362935 | 23.00204105381689 |
| map: rest / current | canvas-land/ring | (172.125,114.750,57.375); (143.090,123.044,64.418) | (216.750,178.500,140.250); (124.730,98.564,21.578) | 3.2184900262970824 | 29.065866043686473 |
| map: rest / selected | canvas-land/ring | (172.125,114.750,57.375); (142.754,109.383,24.975) | (216.750,178.500,140.250); (160.838,128.491,46.670) | 6.029083048722938 | 17.830400053905702 |
| map: rest / hovered | canvas-land/ring | (172.125,114.750,57.375); (143.090,123.044,64.418) | (216.750,178.500,140.250); (88.775,72.937,26.933) | 3.2184900262970824 | 42.10643392805259 |
| map: current / selected | canvas-land/ring | (143.090,123.044,64.418); (142.754,109.383,24.975) | (124.730,98.564,21.578); (160.838,128.491,46.670) | 5.896061714756184 | 12.505148179502337 † |
| map: current / hovered | canvas-land/ring | (143.090,123.044,64.418); (143.090,123.044,64.418) | (124.730,98.564,21.578); (88.775,72.937,26.933) | 0 | 11.515866170801722 † |
| map: selected / hovered | canvas-land/ring | (142.754,109.383,24.975); (143.090,123.044,64.418) | (160.838,128.491,46.670); (88.775,72.937,26.933) | 5.896061714756184 | 23.723286872925648 |
| map: rest / current | sidebar-wash-0/rest/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (111.180,88.230,19.380) | 16.800428551875378 | 33.78819939915812 |
| map: rest / selected | sidebar-wash-0/rest/ring, sidebar-wash-0/hover/ring, sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (208.539,158.282,31.161) | (216.750,178.500,140.250); (156.808,125.265,45.478) | 14.337990382173535 | 18.802722651474767 |
| map: rest / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (75.225,62.602,24.735) | 16.800428551875378 | 48.27946163950227 |
| map: current / selected | sidebar-wash-0/rest/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (111.180,88.230,19.380); (156.808,125.265,45.478) | 6.961704626353169 | 15.558330139839457 |
| map: current / hovered | sidebar-wash-0/rest/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (111.180,88.230,19.380); (75.225,62.602,24.735) | 0 | 11.520929286029334 † |
| map: selected / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (156.808,125.265,45.478); (75.225,62.602,24.735) | 6.961704626353169 | 26.231708947495505 |
| map: rest / current | sidebar-wash-0/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (119.085,94.835,22.695) | 16.800428551875378 | 30.755540892721594 |
| map: rest / hovered | sidebar-wash-0/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (83.130,69.207,28.050) | 16.800428551875378 | 44.42189705951194 |
| map: current / selected | sidebar-wash-0/hover/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (119.085,94.835,22.695); (156.808,125.265,45.478) | 6.961704626353169 | 12.910817334289186 † |
| map: current / hovered | sidebar-wash-0/hover/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (119.085,94.835,22.695); (83.130,69.207,28.050) | 0 | 11.591120026201821 † |
| map: selected / hovered | sidebar-wash-0/hover/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (156.808,125.265,45.478); (83.130,69.207,28.050) | 6.961704626353169 | 23.89416911029727 |
| map: rest / current | sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (120.700,95.338,20.386) | 16.800428551875378 | 30.46445830133711 |
| map: current / selected | sidebar-wash-0/selected-current/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (120.700,95.338,20.386); (156.808,125.265,45.478) | 6.961704626353169 | 12.540776299148078 † |
| map: current / hovered | sidebar-wash-0/selected-current/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (120.700,95.338,20.386); (75.225,62.602,24.735) | 0 | 14.427621695191148 † |
| map: rest / current | sidebar-wash-0.07/rest/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (115.321,89.230,22.474) | 16.800428551875378 | 32.80472584717713 |
| map: rest / selected | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/hover/ring, sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (208.539,158.282,31.161) | (216.750,178.500,140.250); (160.453,126.144,48.201) | 14.337990382173535 | 18.165883508028067 |
| map: rest / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (79.366,63.602,27.829) | 16.800428551875378 | 47.12553812763768 |
| map: current / selected | sidebar-wash-0.07/rest/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (115.321,89.230,22.474); (160.453,126.144,48.201) | 6.961704626353169 | 15.54997924251387 |
| map: current / hovered | sidebar-wash-0.07/rest/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (115.321,89.230,22.474); (79.366,63.602,27.829) | 0 | 11.678325611198328 † |
| map: selected / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (160.453,126.144,48.201); (79.366,63.602,27.829) | 6.961704626353169 | 26.392612297919126 |
| map: rest / current | sidebar-wash-0.07/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (121.156,95.334,24.242) | 16.800428551875378 | 30.291309172729214 |
| map: rest / hovered | sidebar-wash-0.07/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (85.201,69.707,29.597) | 16.800428551875378 | 43.842990427843134 |
| map: current / selected | sidebar-wash-0.07/hover/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (121.156,95.334,24.242); (160.453,126.144,48.201) | 6.961704626353169 | 13.234393380855895 † |
| map: current / hovered | sidebar-wash-0.07/hover/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (121.156,95.334,24.242); (85.201,69.707,29.597) | 0 | 11.667183297212453 † |
| map: selected / hovered | sidebar-wash-0.07/hover/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (160.453,126.144,48.201); (85.201,69.707,29.597) | 6.961704626353169 | 24.330668450317223 |
| map: rest / current | sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (216.750,178.500,140.250); (124.345,96.218,23.109) | 16.800428551875378 | 29.65793850088731 |
| map: current / selected | sidebar-wash-0.07/selected-current/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (124.345,96.218,23.109); (160.453,126.144,48.201) | 6.961704626353169 | 12.53838262764162 † |
| map: current / hovered | sidebar-wash-0.07/selected-current/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (124.345,96.218,23.109); (79.366,63.602,27.829) | 0 | 14.527693476506052 † |

All individual pair/context maxima and maximizing witnesses are in `gilded-joint.json`. Each individual maximum exhausts the two independent state domains; count and witnesses are reported explicitly. They provide context and do not determine joint-exception acceptance. Full-domain coverage exhausts each surface factor and combines all twelve independent state domains exactly.

## Vector

Joint maximum minimum ΔE: **10.191082279599211**. Exhaustive full-domain count: **2834352000000**; satisfying assignments: **0**; changed roots at the selected tie-break: **5**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--state-mem-normal` | `hsl(185 100% 50%)` |
| `--state-mem-over` | `hsl(200 90% 55%)` |
| `--state-delete-unarmed` | `hsl(185 40% 55%)` |
| `--state-delete-armed` | `hsl(350 80% 55%)` |
| `--state-map-rest` | `hsl(200 100% 40%)` |
| `--state-map-current` | `hsl(190 100% 40%)` |
| `--state-map-selected` | `hsl(185 100% 50%)` |
| `--state-map-hovered` | `hsl(190 80% 30%)` |
| `--state-key-absent` | `hsl(185 30% 30%)` |
| `--state-key-missing` | `hsl(200 90% 55%)` |
| `--state-key-present` | `hsl(185 40% 55%)` |
| `--state-key-verified` | `hsl(185 100% 70%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (0.000,233.750,255.000); (36.975,174.675,243.525) | (0.000,233.750,255.000); (36.975,174.675,243.525) | 14.40404073730409 | 14.40404073730409 † |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (94.350,178.500,186.150); (232.050,48.450,79.050) | (94.350,178.500,186.150); (232.050,48.450,79.050) | 34.19818261757641 | 34.19818261757641 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (36.503,68.939,71.617); (84.698,23.422,34.132) | (36.503,68.939,71.617); (84.698,23.422,34.132) | 16.408197999576796 | 16.408197999576796 |
| key: optional-absent / required-missing | required/rest, optional/rest | (38.378,68.722,71.273); (36.975,174.675,243.525) | (29.452,52.785,54.697); (36.975,174.675,243.525) | 41.3508836007381 | 45.47510490045781 |
| key: optional-absent / present | required/rest | (38.378,68.722,71.273); (94.350,178.500,186.150) | (29.452,52.785,54.697); (94.350,178.500,186.150) | 39.08973543617644 | 43.34071736879887 |
| key: optional-absent / verified | required/rest | (38.378,68.722,71.273); (0.000,233.750,255.000) | (29.452,52.785,54.697); (102.000,242.250,255.000) | 54.864998719819546 | 65.7530991551755 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (36.975,174.675,243.525); (94.350,178.500,186.150) | (36.975,174.675,243.525); (94.350,178.500,186.150) | 13.513540821543312 | 13.513540821543312 † |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (36.975,174.675,243.525); (0.000,233.750,255.000) | (36.975,174.675,243.525); (102.000,242.250,255.000) | 14.40404073730409 | 18.36967637502241 |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (94.350,178.500,186.150); (0.000,233.750,255.000) | (94.350,178.500,186.150); (102.000,242.250,255.000) | 13.427931019604726 | 14.846818606019937 † |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (36.975,174.675,243.525) | (53.550,95.625,99.450); (36.975,174.675,243.525) | 21.78575194244601 | 32.88683704262142 |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (94.350,178.500,186.150) | (53.550,95.625,99.450); (94.350,178.500,186.150) | 16.28884750990673 | 29.55023624894975 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (0.000,233.750,255.000) | (53.550,95.625,99.450); (102.000,242.250,255.000) | 28.837735721157593 | 43.275645948677685 |
| key: optional-absent / present | optional/rest | (38.378,68.722,71.273); (49.853,94.222,98.047) | (29.452,52.785,54.697); (49.853,94.222,98.047) | 7.90901489803421 | 12.672203866904772 † |
| key: optional-absent / verified | optional/rest | (38.378,68.722,71.273); (2.677,121.847,132.472) | (29.452,52.785,54.697); (53.677,126.097,132.472) | 16.70177044513478 | 22.924342811299475 |
| key: required-missing / present | optional/rest | (36.975,174.675,243.525); (49.853,94.222,98.047) | (36.975,174.675,243.525); (49.853,94.222,98.047) | 33.47067227577112 | 33.47067227577112 |
| key: required-missing / verified | optional/rest | (36.975,174.675,243.525); (2.677,121.847,132.472) | (36.975,174.675,243.525); (53.677,126.097,132.472) | 22.928891098979445 | 21.974192194719148 |
| key: present / verified | optional/rest | (49.853,94.222,98.047); (2.677,121.847,132.472) | (49.853,94.222,98.047); (53.677,126.097,132.472) | 9.18874139605276 | 10.452122097547305 † |
| map: rest / current | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (0.000,170.000,204.000) | 10.395684302399912 | 10.766655110054554 † |
| map: rest / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (36.975,174.675,243.525); (0.000,233.750,255.000) | (0.000,136.000,204.000); (0.000,233.750,255.000) | 14.40404073730409 | 25.295466866782746 |
| map: rest / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (15.300,117.300,137.700) | 10.395684302399912 | 12.46475883563715 † |
| map: current / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (71.400,207.400,234.600); (0.000,233.750,255.000) | (0.000,170.000,204.000); (0.000,233.750,255.000) | 4.965188543168605 | 15.33312030196306 |
| map: current / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (71.400,207.400,234.600); (71.400,207.400,234.600) | (0.000,170.000,204.000); (15.300,117.300,137.700) | 0 | 18.515914489242054 |
| map: selected / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (0.000,233.750,255.000); (71.400,207.400,234.600) | (0.000,233.750,255.000); (15.300,117.300,137.700) | 4.965188543168605 | 32.7907370230873 |
| map: rest / current | canvas-sea/ring | (36.975,174.675,243.525); (45.696,129.744,146.064) | (0.000,136.000,204.000); (2.856,107.304,127.704) | 18.930499550985033 | 14.942219201204104 † |
| map: rest / selected | canvas-sea/ring | (36.975,174.675,243.525); (2.856,145.554,158.304) | (0.000,136.000,204.000); (2.856,145.554,158.304) | 15.396008028838208 | 10.725268640945693 † |
| map: rest / hovered | canvas-sea/ring | (36.975,174.675,243.525); (45.696,129.744,146.064) | (0.000,136.000,204.000); (12.036,75.684,87.924) | 18.930499550985033 | 24.576327743184287 |
| map: current / selected | canvas-sea/ring | (45.696,129.744,146.064); (2.856,145.554,158.304) | (2.856,107.304,127.704); (2.856,145.554,158.304) | 4.445290058625113 | 12.800218219644188 † |
| map: current / hovered | canvas-sea/ring | (45.696,129.744,146.064); (45.696,129.744,146.064) | (2.856,107.304,127.704); (12.036,75.684,87.924) | 0 | 10.255860725125089 † |
| map: selected / hovered | canvas-sea/ring | (2.856,145.554,158.304); (45.696,129.744,146.064) | (2.856,145.554,158.304); (12.036,75.684,87.924) | 4.445290058625113 | 22.280890198956502 |
| map: rest / current | canvas-land/ring | (36.975,174.675,243.525); (45.239,143.855,161.535) | (0.000,136.000,204.000); (2.399,121.415,143.175) | 14.733918447473032 | 11.2337385791659 † |
| map: rest / selected | canvas-land/ring | (36.975,174.675,243.525); (2.399,159.665,173.775) | (0.000,136.000,204.000); (2.399,159.665,173.775) | 12.011793394387016 | 11.501627331108317 † |
| map: rest / hovered | canvas-land/ring | (36.975,174.675,243.525); (45.239,143.855,161.535) | (0.000,136.000,204.000); (11.579,89.795,103.395) | 14.733918447473032 | 20.71567564084519 |
| map: current / selected | canvas-land/ring | (45.239,143.855,161.535); (2.399,159.665,173.775) | (2.399,121.415,143.175); (2.399,159.665,173.775) | 4.220056042499549 | 12.928976942613831 † |
| map: current / hovered | canvas-land/ring | (45.239,143.855,161.535); (45.239,143.855,161.535) | (2.399,121.415,143.175); (11.579,89.795,103.395) | 0 | 10.599936455987908 † |
| map: selected / hovered | canvas-land/ring | (2.399,159.665,173.775); (45.239,143.855,161.535) | (2.399,159.665,173.775); (11.579,89.795,103.395) | 4.220056042499549 | 23.52032063983843 |
| map: rest / current | sidebar-wash-0/rest/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (2.142,105.978,126.378) | 10.395684302399912 | 15.284640049705944 |
| map: rest / selected | sidebar-wash-0/rest/ring, sidebar-wash-0/hover/ring, sidebar-wash-0/selected-current/ring | (36.975,174.675,243.525); (0.000,233.750,255.000) | (0.000,136.000,204.000); (1.885,154.971,168.741) | 14.40404073730409 | 11.020413627731111 † |
| map: rest / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (11.322,74.358,86.598) | 10.395684302399912 | 24.916400427982772 |
| map: current / selected | sidebar-wash-0/rest/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (2.142,105.978,126.378); (1.885,154.971,168.741) | 4.965188543168605 | 16.664971854533796 |
| map: current / hovered | sidebar-wash-0/rest/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (2.142,105.978,126.378); (11.322,74.358,86.598) | 0 | 10.227139384751426 † |
| map: selected / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (0.000,233.750,255.000); (71.400,207.400,234.600) | (1.885,154.971,168.741); (11.322,74.358,86.598) | 4.965188543168605 | 26.14550848588385 |
| map: rest / current | sidebar-wash-0/hover/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (4.641,114.104,135.099) | 10.395684302399912 | 13.112952655644994 † |
| map: rest / hovered | sidebar-wash-0/hover/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (13.821,82.484,95.319) | 10.395684302399912 | 22.72323531107391 |
| map: current / selected | sidebar-wash-0/hover/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (4.641,114.104,135.099); (1.885,154.971,168.741) | 4.965188543168605 | 13.942622875477882 † |
| map: current / hovered | sidebar-wash-0/hover/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (4.641,114.104,135.099); (13.821,82.484,95.319) | 0 | 10.404706975461979 † |
| map: selected / hovered | sidebar-wash-0/hover/ring | (0.000,233.750,255.000); (71.400,207.400,234.600) | (1.885,154.971,168.741); (13.821,82.484,95.319) | 4.965188543168605 | 23.813915762457516 |
| map: rest / current | sidebar-wash-0/selected-current/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (1.885,116.721,138.141) | 10.395684302399912 | 12.393880918884403 † |
| map: current / selected | sidebar-wash-0/selected-current/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (1.885,116.721,138.141); (1.885,154.971,168.741) | 4.965188543168605 | 13.07269238013569 † |
| map: current / hovered | sidebar-wash-0/selected-current/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (1.885,116.721,138.141); (11.322,74.358,86.598) | 0 | 13.654501042998376 † |
| map: rest / current | sidebar-wash-0.07/rest/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (6.419,106.985,129.479) | 10.395684302399912 | 14.625351359602886 † |
| map: rest / selected | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/hover/ring, sidebar-wash-0.07/selected-current/ring | (36.975,174.675,243.525); (0.000,233.750,255.000) | (0.000,136.000,204.000); (5.649,155.857,171.470) | 14.40404073730409 | 10.749553740218175 † |
| map: rest / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (15.599,75.365,89.699) | 10.395684302399912 | 24.251485619575828 |
| map: current / selected | sidebar-wash-0.07/rest/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (6.419,106.985,129.479); (5.649,155.857,171.470) | 4.965188543168605 | 16.64036321212006 |
| map: current / hovered | sidebar-wash-0.07/rest/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (6.419,106.985,129.479); (15.599,75.365,89.699) | 0 | 10.191082279599211 † |
| map: selected / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (0.000,233.750,255.000); (71.400,207.400,234.600) | (5.649,155.857,171.470); (15.599,75.365,89.699) | 4.965188543168605 | 26.139050345874058 |
| map: rest / current | sidebar-wash-0.07/hover/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (6.779,114.607,136.650) | 10.395684302399912 | 12.77576128492695 † |
| map: rest / hovered | sidebar-wash-0.07/hover/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (15.959,82.987,96.870) | 10.395684302399912 | 22.385098845782764 |
| map: current / selected | sidebar-wash-0.07/hover/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (6.779,114.607,136.650); (5.649,155.857,171.470) | 4.965188543168605 | 14.092960406991288 † |
| map: current / hovered | sidebar-wash-0.07/hover/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (6.779,114.607,136.650); (15.959,82.987,96.870) | 0 | 10.39004184224066 † |
| map: selected / hovered | sidebar-wash-0.07/hover/ring | (0.000,233.750,255.000); (71.400,207.400,234.600) | (5.649,155.857,171.470); (15.959,82.987,96.870) | 4.965188543168605 | 24.050257546660937 |
| map: rest / current | sidebar-wash-0.07/selected-current/ring | (36.975,174.675,243.525); (71.400,207.400,234.600) | (0.000,136.000,204.000); (5.649,117.607,140.870) | 10.395684302399912 | 11.801343386414962 † |
| map: current / selected | sidebar-wash-0.07/selected-current/ring | (71.400,207.400,234.600); (0.000,233.750,255.000) | (5.649,117.607,140.870); (5.649,155.857,171.470) | 4.965188543168605 | 13.038078744521949 † |
| map: current / hovered | sidebar-wash-0.07/selected-current/ring | (71.400,207.400,234.600); (71.400,207.400,234.600) | (5.649,117.607,140.870); (15.599,75.365,89.699) | 0 | 13.559758990404873 † |

All individual pair/context maxima and maximizing witnesses are in `vector-joint.json`. Each individual maximum exhausts the two independent state domains; count and witnesses are reported explicitly. They provide context and do not determine joint-exception acceptance. Full-domain coverage exhausts each surface factor and combines all twelve independent state domains exactly.
