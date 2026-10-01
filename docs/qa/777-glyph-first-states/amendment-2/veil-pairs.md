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
