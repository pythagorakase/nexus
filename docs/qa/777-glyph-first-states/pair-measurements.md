# Complete Before/After Pair Measurements

## Veil

Joint maximum minimum ΔE: **8.464152824101713**. Exhaustive full-domain count: **10935000**; satisfying assignments: **0**; changed roots at the selected tie-break: **5**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--brass` | `#b83d7a` |
| `--bronze` | `hsl(15 75% 60%)` |
| `--brass-bright` | `hsl(330.2439024390244 60% 30%)` |
| `--map-hovered` | `hsl(330.2439024390244 60% 70%)` |
| `--fg-muted` | `hsl(42 30% 65%)` |
| `--fg-dim` | `hsl(42 20% 30%)` |
| `--destructive` | `hsl(0 80% 50%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (189.720,55.080,144.840); (229.500,114.750,76.500) | (184.000,61.000,122.000); (229.500,114.750,76.500) | 38.002783748871494 | 28.68503954807603 |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (192.525,176.460,138.975); (210.375,44.625,44.625) | (192.525,176.460,138.975); (229.500,25.500,25.500) | 20.80376452918997 | 20.37987230073326 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (73.351,70.380,62.564); (79.598,24.238,29.542) | (73.351,70.380,62.564); (86.292,17.544,22.848) | 9.51238876756636 | 11.405805656799993 † |
| key: optional-absent / required-missing | required/rest, optional/rest | (81.090,75.480,61.710); (229.500,114.750,76.500) | (50.490,47.940,41.310); (229.500,114.750,76.500) | 35.826832286531086 | 44.872497956263594 |
| key: optional-absent / present | required/rest | (81.090,75.480,61.710); (192.525,176.460,138.975) | (50.490,47.940,41.310); (192.525,176.460,138.975) | 40.38140915874647 | 52.526701496627574 |
| key: optional-absent / verified | required/rest | (81.090,75.480,61.710); (189.720,55.080,144.840) | (50.490,47.940,41.310); (184.000,61.000,122.000) | 24.91703362959893 | 24.380998649311447 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (229.500,114.750,76.500); (192.525,176.460,138.975) | (229.500,114.750,76.500); (192.525,176.460,138.975) | 11.447234141252315 | 11.447234141252315 † |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (184.000,61.000,122.000) | 38.002783748871494 | 28.68503954807603 |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (192.525,176.460,138.975); (189.720,55.080,144.840) | (192.525,176.460,138.975); (184.000,61.000,122.000) | 33.74473623257419 | 26.920280531182737 |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (229.500,114.750,76.500) | (91.800,82.620,61.200); (229.500,114.750,76.500) | 10.828932806147856 | 31.719112839573807 |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (192.525,176.460,138.975) | (91.800,82.620,61.200); (192.525,176.460,138.975) | 11.904163763235427 | 35.782078723358694 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (153.000,137.700,102.000); (189.720,55.080,144.840) | (91.800,82.620,61.200); (184.000,61.000,122.000) | 28.357466144039577 | 17.508479557427986 |
| key: optional-absent / present | optional/rest | (81.090,75.480,61.710); (100.853,94.860,80.198) | (50.490,47.940,41.310); (100.853,94.860,80.198) | 6.861207612606855 | 16.43521788919975 |
| key: optional-absent / verified | optional/rest | (81.090,75.480,61.710); (99.450,34.170,83.130) | (50.490,47.940,41.310); (96.590,37.130,71.710) | 18.76076985549963 | 10.403305932066703 † |
| key: required-missing / present | optional/rest | (229.500,114.750,76.500); (100.853,94.860,80.198) | (229.500,114.750,76.500); (100.853,94.860,80.198) | 28.46237996653055 | 28.46237996653055 |
| key: required-missing / verified | optional/rest | (229.500,114.750,76.500); (99.450,34.170,83.130) | (229.500,114.750,76.500); (96.590,37.130,71.710) | 49.861998154488546 | 46.28426679252508 |
| key: present / verified | optional/rest | (100.853,94.860,80.198); (99.450,34.170,83.130) | (100.853,94.860,80.198); (96.590,37.130,71.710) | 21.55216217024095 | 17.43406921843264 |
| map: rest / current | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (122.400,30.600,76.127) | 36.519036034009964 | 40.238029984278675 |
| map: rest / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (184.000,61.000,122.000) | 38.002783748871494 | 28.68503954807603 |
| map: rest / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (224.400,132.600,178.127) | 36.519036034009964 | 28.154921869576675 |
| map: current / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (214.200,91.800,173.400); (189.720,55.080,144.840) | (122.400,30.600,76.127); (184.000,61.000,122.000) | 9.571575278395933 | 15.618186802122327 |
| map: current / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (214.200,91.800,173.400); (214.200,91.800,173.400) | (122.400,30.600,76.127); (224.400,132.600,178.127) | 0 | 37.60960617716947 |
| map: selected / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (189.720,55.080,144.840); (214.200,91.800,173.400) | (184.000,61.000,122.000); (224.400,132.600,178.127) | 9.571575278395933 | 17.854502924461286 |
| map: rest / current | canvas-sea/ring | (229.500,114.750,76.500); (131.580,59.500,111.180) | (229.500,114.750,76.500); (76.500,22.780,52.816) | 43.28622726344373 | 48.996593369389224 |
| map: rest / selected | canvas-sea/ring | (229.500,114.750,76.500); (116.892,37.468,94.044) | (229.500,114.750,76.500); (113.460,41.020,80.340) | 47.47355255794096 | 43.0749887986686 |
| map: rest / hovered | canvas-sea/ring | (229.500,114.750,76.500); (131.580,59.500,111.180) | (229.500,114.750,76.500); (137.700,83.980,114.016) | 43.28622726344373 | 34.59266107687331 |
| map: current / selected | canvas-sea/ring | (131.580,59.500,111.180); (116.892,37.468,94.044) | (76.500,22.780,52.816); (113.460,41.020,80.340) | 5.619200746846419 | 8.464152824101713 † |
| map: current / hovered | canvas-sea/ring | (131.580,59.500,111.180); (131.580,59.500,111.180) | (76.500,22.780,52.816); (137.700,83.980,114.016) | 0 | 19.649975786657986 |
| map: selected / hovered | canvas-sea/ring | (116.892,37.468,94.044); (131.580,59.500,111.180) | (113.460,41.020,80.340); (137.700,83.980,114.016) | 5.619200746846419 | 11.309863328013883 † |
| map: rest / current | canvas-land/ring | (229.500,114.750,76.500); (143.232,62.318,119.307) | (229.500,114.750,76.500); (87.786,25.977,59.482) | 41.67385657003848 | 47.08558551657648 |
| map: rest / selected | canvas-land/ring | (229.500,114.750,76.500); (128.544,40.286,102.171) | (229.500,114.750,76.500); (124.746,44.217,87.006) | 45.82269295419665 | 40.883687368205955 |
| map: rest / hovered | canvas-land/ring | (229.500,114.750,76.500); (143.232,62.318,119.307) | (229.500,114.750,76.500); (148.986,87.177,120.682) | 41.67385657003848 | 32.96133700388478 |
| map: current / selected | canvas-land/ring | (143.232,62.318,119.307); (128.544,40.286,102.171) | (87.786,25.977,59.482); (124.746,44.217,87.006) | 5.687471528003299 | 8.599541734342413 † |
| map: current / hovered | canvas-land/ring | (143.232,62.318,119.307); (143.232,62.318,119.307) | (87.786,25.977,59.482); (148.986,87.177,120.682) | 0 | 19.93256331944886 |
| map: selected / hovered | canvas-land/ring | (128.544,40.286,102.171); (143.232,62.318,119.307) | (124.746,44.217,87.006); (148.986,87.177,120.682) | 5.687471528003299 | 11.472092210185755 † |
| map: rest / current | sidebar-wash-0/rest/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (77.112,23.664,54.244) | 36.519036034009964 | 49.13640338458866 |
| map: rest / selected | sidebar-wash-0/rest/ring, sidebar-wash-0/hover/ring, sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (122.463,44.196,86.596) | 38.002783748871494 | 41.56526497223401 |
| map: rest / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (138.312,84.864,115.444) | 36.519036034009964 | 34.7057470068627 |
| map: current / selected | sidebar-wash-0/rest/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (77.112,23.664,54.244); (122.463,44.196,86.596) | 9.571575278395933 | 10.209668184786667 † |
| map: current / hovered | sidebar-wash-0/rest/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (77.112,23.664,54.244); (138.312,84.864,115.444) | 0 | 19.717192574370937 |
| map: selected / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (122.463,44.196,86.596); (138.312,84.864,115.444) | 9.571575278395933 | 9.664649463755982 † |
| map: rest / current | sidebar-wash-0/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (83.436,27.132,60.160) | 36.519036034009964 | 48.51688796069563 |
| map: rest / hovered | sidebar-wash-0/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (144.636,88.332,121.360) | 36.519036034009964 | 34.16746537197732 |
| map: current / selected | sidebar-wash-0/hover/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (83.436,27.132,60.160); (122.463,44.196,86.596) | 9.571575278395933 | 8.751486223011998 † |
| map: current / hovered | sidebar-wash-0/hover/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (83.436,27.132,60.160); (144.636,88.332,121.360) | 0 | 20.001085826914565 |
| map: selected / hovered | sidebar-wash-0/hover/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (122.463,44.196,86.596); (144.636,88.332,121.360) | 9.571575278395933 | 11.494015812497988 † |
| map: rest / current | sidebar-wash-0/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (85.503,25.956,59.072) | 36.519036034009964 | 47.69734013188648 |
| map: current / selected | sidebar-wash-0/selected-current/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (85.503,25.956,59.072); (122.463,44.196,86.596) | 9.571575278395933 | 8.578168329881416 † |
| map: current / hovered | sidebar-wash-0/selected-current/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (85.503,25.956,59.072); (138.312,84.864,115.444) | 0 | 18.13299144707518 |
| map: rest / current | sidebar-wash-0.07/rest/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (81.282,24.578,57.024) | 36.519036034009964 | 48.61053676077338 |
| map: rest / selected | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/hover/ring, sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (189.720,55.080,144.840) | (229.500,114.750,76.500); (126.133,45.000,89.042) | 38.002783748871494 | 40.988409103261446 |
| map: rest / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (142.482,85.778,118.224) | 36.519036034009964 | 34.336586923966884 |
| map: current / selected | sidebar-wash-0.07/rest/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (81.282,24.578,57.024); (126.133,45.000,89.042) | 9.571575278395933 | 10.165704238175673 † |
| map: current / hovered | sidebar-wash-0.07/rest/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (81.282,24.578,57.024); (142.482,85.778,118.224) | 0 | 19.791932633485917 |
| map: selected / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (126.133,45.000,89.042); (142.482,85.778,118.224) | 9.571575278395933 | 9.792799419124654 † |
| map: rest / current | sidebar-wash-0.07/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (85.521,27.589,61.550) | 36.519036034009964 | 48.25647853520175 |
| map: rest / hovered | sidebar-wash-0.07/hover/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (146.721,88.789,122.750) | 36.519036034009964 | 34.01217385052332 |
| map: current / selected | sidebar-wash-0.07/hover/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (85.521,27.589,61.550); (126.133,45.000,89.042) | 9.571575278395933 | 9.102842433426318 † |
| map: current / hovered | sidebar-wash-0.07/hover/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (85.521,27.589,61.550); (146.721,88.789,122.750) | 0 | 20.044674569363643 |
| map: selected / hovered | sidebar-wash-0.07/hover/ring | (189.720,55.080,144.840); (214.200,91.800,173.400) | (126.133,45.000,89.042); (146.721,88.789,122.750) | 9.571575278395933 | 11.189304283223962 † |
| map: rest / current | sidebar-wash-0.07/selected-current/ring | (229.500,114.750,76.500); (214.200,91.800,173.400) | (229.500,114.750,76.500); (89.173,26.760,61.518) | 36.519036034009964 | 47.2284950738192 |
| map: current / selected | sidebar-wash-0.07/selected-current/ring | (214.200,91.800,173.400); (189.720,55.080,144.840) | (89.173,26.760,61.518); (126.133,45.000,89.042) | 9.571575278395933 | 8.621886496932001 † |
| map: current / hovered | sidebar-wash-0.07/selected-current/ring | (214.200,91.800,173.400); (214.200,91.800,173.400) | (89.173,26.760,61.518); (142.482,85.778,118.224) | 0 | 18.297304492594847 |

All individual pair/context maxima and maximizing witnesses are in `veil-joint.json`. Maxima enumerate full factor domains (including irrelevant roots); the factor count is reported explicitly. They provide context and do not determine joint-exception acceptance. Historical opaque map-fill maxima remain in `map-fill-search.json`.

## Gilded

Joint maximum minimum ΔE: **9.665520083366916**. Exhaustive full-domain count: **236196000**; satisfying assignments: **0**; changed roots at the selected tie-break: **7**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--brass` | `hsl(43 74% 40%)` |
| `--bronze` | `hsl(30 50% 60%)` |
| `--brass-bright` | `hsl(45 55% 30%)` |
| `--map-hovered` | `hsl(45 75% 60%)` |
| `--fg-muted` | `hsl(43 40% 30%)` |
| `--fg-dim` | `hsl(43 30% 70%)` |
| `--destructive` | `hsl(0 100% 50%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (208.539,158.282,31.161); (172.125,114.750,57.375) | (177.480,134.708,26.520); (204.000,153.000,102.000) | 14.337990382173535 | 9.906070273441152 † |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (181.560,153.816,83.640); (195.075,34.425,34.425) | (107.100,89.760,45.900); (255.000,0.000,0.000) | 17.039081906673687 | 23.36206185340384 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (70.176,60.466,35.904); (74.906,18.679,18.679) | (44.115,38.046,22.695); (95.880,6.630,6.630) | 6.273849550380767 | 10.201121553574538 † |
| key: optional-absent / required-missing | required/rest, optional/rest | (71.400,62.730,40.800); (172.125,114.750,57.375) | (105.825,99.323,82.875); (204.000,153.000,102.000) | 27.558605649270802 | 27.378445894110573 |
| key: optional-absent / present | required/rest | (71.400,62.730,40.800); (181.560,153.816,83.640) | (105.825,99.323,82.875); (107.100,89.760,45.900) | 38.88438534602612 | 9.665520083366916 † |
| key: optional-absent / verified | required/rest | (71.400,62.730,40.800); (208.539,158.282,31.161) | (105.825,99.323,82.875); (177.480,134.708,26.520) | 45.991602192291126 | 25.618054002176063 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (181.560,153.816,83.640) | (204.000,153.000,102.000); (107.100,89.760,45.900) | 9.20305994887555 | 27.979120217976284 |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (208.539,158.282,31.161) | (204.000,153.000,102.000); (177.480,134.708,26.520) | 14.337990382173535 | 9.906070273441152 † |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (181.560,153.816,83.640); (208.539,158.282,31.161) | (107.100,89.760,45.900); (177.480,134.708,26.520) | 8.084904016113446 | 23.022523885888248 |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (172.125,114.750,57.375) | (201.450,188.445,155.550); (204.000,153.000,102.000) | 7.72892192098335 | 9.96812603486925 † |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (181.560,153.816,83.640) | (201.450,188.445,155.550); (107.100,89.760,45.900) | 15.32055288939221 | 34.10385971482208 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (208.539,158.282,31.161) | (201.450,188.445,155.550); (177.480,134.708,26.520) | 21.598012943420677 | 19.541225709093233 |
| key: optional-absent / present | optional/rest | (71.400,62.730,40.800); (95.880,82.008,46.920) | (105.825,99.323,82.875); (58.650,49.980,28.050) | 8.110992474373157 | 16.931196893012313 |
| key: optional-absent / verified | optional/rest | (71.400,62.730,40.800); (109.370,84.241,20.680) | (105.825,99.323,82.875); (93.840,72.454,18.360) | 13.774703240065797 | 14.210069995423318 † |
| key: required-missing / present | optional/rest | (172.125,114.750,57.375); (95.880,82.008,46.920) | (204.000,153.000,102.000); (58.650,49.980,28.050) | 19.807242349119495 | 45.53712041942352 |
| key: required-missing / verified | optional/rest | (172.125,114.750,57.375); (109.370,84.241,20.680) | (204.000,153.000,102.000); (93.840,72.454,18.360) | 16.41371532037838 | 35.57420031583928 |
| key: present / verified | optional/rest | (95.880,82.008,46.920); (109.370,84.241,20.680) | (58.650,49.980,28.050); (93.840,72.454,18.360) | 6.779403334981554 | 12.129626840316082 † |
| map: rest / current | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (118.575,97.538,34.425) | 16.800428551875378 | 23.802879800882927 |
| map: rest / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (208.539,158.282,31.161) | (204.000,153.000,102.000); (177.480,134.708,26.520) | 14.337990382173535 | 9.906070273441152 † |
| map: rest / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (229.500,191.250,76.500) | 16.800428551875378 | 11.63473675430485 † |
| map: current / selected | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (209.100,181.050,96.900); (208.539,158.282,31.161) | (118.575,97.538,34.425); (177.480,134.708,26.520) | 6.961704626353169 | 18.166842185552806 |
| map: current / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (209.100,181.050,96.900); (209.100,181.050,96.900) | (118.575,97.538,34.425); (229.500,191.250,76.500) | 0 | 32.69701409478548 |
| map: selected / hovered | canvas-sea/fill, canvas-land/fill, sidebar-wash-0/rest/fill, sidebar-wash-0/hover/fill, sidebar-wash-0/selected-current/fill, sidebar-wash-0.07/rest/fill, sidebar-wash-0.07/hover/fill, sidebar-wash-0.07/selected-current/fill | (208.539,158.282,31.161); (209.100,181.050,96.900) | (177.480,134.708,26.520); (229.500,191.250,76.500) | 6.961704626353169 | 15.4278857396218 |
| map: rest / current | canvas-sea/ring | (172.125,114.750,57.375); (130.560,113.730,63.240) | (204.000,153.000,102.000); (76.245,63.623,25.755) | 7.326844090326136 | 40.46476001678662 |
| map: rest / selected | canvas-sea/ring | (172.125,114.750,57.375); (130.223,100.069,23.797) | (204.000,153.000,102.000); (111.588,85.925,21.012) | 9.862954046610353 | 28.46860974457199 |
| map: rest / hovered | canvas-sea/ring | (172.125,114.750,57.375); (130.560,113.730,63.240) | (204.000,153.000,102.000); (142.800,119.850,51.000) | 7.326844090326136 | 14.459504861160388 † |
| map: current / selected | canvas-sea/ring | (130.560,113.730,63.240); (130.223,100.069,23.797) | (76.245,63.623,25.755); (111.588,85.925,21.012) | 6.3659257084362935 | 10.68111820753669 † |
| map: current / hovered | canvas-sea/ring | (130.560,113.730,63.240); (130.560,113.730,63.240) | (76.245,63.623,25.755); (142.800,119.850,51.000) | 0 | 22.16047170035347 |
| map: selected / hovered | canvas-sea/ring | (130.223,100.069,23.797); (130.560,113.730,63.240) | (111.588,85.925,21.012); (142.800,119.850,51.000) | 6.3659257084362935 | 12.51240364554908 † |
| map: rest / current | canvas-land/ring | (172.125,114.750,57.375); (143.090,123.044,64.418) | (204.000,153.000,102.000); (86.788,71.428,26.636) | 3.2184900262970824 | 36.99829211105853 |
| map: rest / selected | canvas-land/ring | (172.125,114.750,57.375); (142.754,109.383,24.975) | (204.000,153.000,102.000); (122.131,93.730,21.893) | 6.029083048722938 | 24.51172481154317 |
| map: rest / hovered | canvas-land/ring | (172.125,114.750,57.375); (143.090,123.044,64.418) | (204.000,153.000,102.000); (153.343,127.655,51.881) | 3.2184900262970824 | 11.547353397094195 † |
| map: current / selected | canvas-land/ring | (143.090,123.044,64.418); (142.754,109.383,24.975) | (86.788,71.428,26.636); (122.131,93.730,21.893) | 5.896061714756184 | 10.612118242348798 † |
| map: current / hovered | canvas-land/ring | (143.090,123.044,64.418); (143.090,123.044,64.418) | (86.788,71.428,26.636); (153.343,127.655,51.881) | 0 | 22.76656421623055 |
| map: selected / hovered | canvas-land/ring | (142.754,109.383,24.975); (143.090,123.044,64.418) | (122.131,93.730,21.893); (153.343,127.655,51.881) | 5.896061714756184 | 12.858861432707167 † |
| map: rest / current | sidebar-wash-0/rest/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (75.225,62.602,24.735) | 16.800428551875378 | 40.806634841675645 |
| map: rest / selected | sidebar-wash-0/rest/ring, sidebar-wash-0/hover/ring, sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (208.539,158.282,31.161) | (204.000,153.000,102.000); (118.597,90.881,20.775) | 14.337990382173535 | 25.88107713132474 |
| map: rest / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (141.780,118.830,49.980) | 16.800428551875378 | 14.846096648163911 † |
| map: current / selected | sidebar-wash-0/rest/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (75.225,62.602,24.735); (118.597,90.881,20.775) | 6.961704626353169 | 13.086624506783153 † |
| map: current / hovered | sidebar-wash-0/rest/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (75.225,62.602,24.735); (141.780,118.830,49.980) | 0 | 22.07819467098016 |
| map: selected / hovered | sidebar-wash-0/rest/ring, sidebar-wash-0/selected-current/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (118.597,90.881,20.775); (141.780,118.830,49.980) | 6.961704626353169 | 10.099540526619462 † |
| map: rest / current | sidebar-wash-0/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (83.130,69.207,28.050) | 16.800428551875378 | 38.17316160130011 |
| map: rest / hovered | sidebar-wash-0/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (149.685,125.434,53.295) | 16.800428551875378 | 12.348993796141103 † |
| map: current / selected | sidebar-wash-0/hover/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (83.130,69.207,28.050); (118.597,90.881,20.775) | 6.961704626353169 | 10.726075097369451 † |
| map: current / hovered | sidebar-wash-0/hover/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (83.130,69.207,28.050); (149.685,125.434,53.295) | 0 | 22.59499231858965 |
| map: selected / hovered | sidebar-wash-0/hover/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (118.597,90.881,20.775); (149.685,125.434,53.295) | 6.961704626353169 | 12.938905636592375 † |
| map: rest / current | sidebar-wash-0/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (83.254,68.579,25.518) | 16.800428551875378 | 38.29293043977046 |
| map: current / selected | sidebar-wash-0/selected-current/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (83.254,68.579,25.518); (118.597,90.881,20.775) | 6.961704626353169 | 10.58507432713944 † |
| map: current / hovered | sidebar-wash-0/selected-current/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (83.254,68.579,25.518); (141.780,118.830,49.980) | 0 | 19.712546427659344 |
| map: rest / current | sidebar-wash-0.07/rest/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (79.366,63.602,27.829) | 16.800428551875378 | 40.114713431798116 |
| map: rest / selected | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/hover/ring, sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (208.539,158.282,31.161) | (204.000,153.000,102.000); (122.242,91.761,23.498) | 14.337990382173535 | 25.008538353937098 |
| map: rest / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (145.921,119.830,53.074) | 16.800428551875378 | 14.037866750179058 † |
| map: current / selected | sidebar-wash-0.07/rest/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (79.366,63.602,27.829); (122.242,91.761,23.498) | 6.961704626353169 | 13.183178944475456 † |
| map: current / hovered | sidebar-wash-0.07/rest/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (79.366,63.602,27.829); (145.921,119.830,53.074) | 0 | 22.26940370982446 |
| map: selected / hovered | sidebar-wash-0.07/rest/ring, sidebar-wash-0.07/selected-current/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (122.242,91.761,23.498); (145.921,119.830,53.074) | 6.961704626353169 | 10.266176964731589 † |
| map: rest / current | sidebar-wash-0.07/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (85.201,69.707,29.597) | 16.800428551875378 | 37.7560253861954 |
| map: rest / hovered | sidebar-wash-0.07/hover/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (151.756,125.934,54.842) | 16.800428551875378 | 11.962085343750624 † |
| map: current / selected | sidebar-wash-0.07/hover/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (85.201,69.707,29.597); (122.242,91.761,23.498) | 6.961704626353169 | 11.048330708764336 † |
| map: current / hovered | sidebar-wash-0.07/hover/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (85.201,69.707,29.597); (151.756,125.934,54.842) | 0 | 22.699856883964028 |
| map: selected / hovered | sidebar-wash-0.07/hover/ring | (208.539,158.282,31.161); (209.100,181.050,96.900) | (122.242,91.761,23.498); (151.756,125.934,54.842) | 6.961704626353169 | 12.657786584542809 † |
| map: rest / current | sidebar-wash-0.07/selected-current/ring | (172.125,114.750,57.375); (209.100,181.050,96.900) | (204.000,153.000,102.000); (86.899,69.459,28.241) | 16.800428551875378 | 37.550941197043755 |
| map: current / selected | sidebar-wash-0.07/selected-current/ring | (209.100,181.050,96.900); (208.539,158.282,31.161) | (86.899,69.459,28.241); (122.242,91.761,23.498) | 6.961704626353169 | 10.714193555693035 † |
| map: current / hovered | sidebar-wash-0.07/selected-current/ring | (209.100,181.050,96.900); (209.100,181.050,96.900) | (86.899,69.459,28.241); (145.921,119.830,53.074) | 0 | 19.958207425952253 |

All individual pair/context maxima and maximizing witnesses are in `gilded-joint.json`. Maxima enumerate full factor domains (including irrelevant roots); the factor count is reported explicitly. They provide context and do not determine joint-exception acceptance. Historical opaque map-fill maxima remain in `map-fill-search.json`.

## Vector

Joint maximum minimum ΔE: **10.191082279599211**. Exhaustive full-domain count: **43740000**; satisfying assignments: **0**; changed roots at the selected tie-break: **5**. One theme exception.

| Root | Shipped Value |
|---|---|
| `--brass` | `hsl(185 100% 50%)` |
| `--bronze` | `hsl(200 100% 40%)` |
| `--brass-bright` | `hsl(190 100% 40%)` |
| `--map-hovered` | `hsl(190 80% 30%)` |
| `--fg-muted` | `hsl(185 40% 50%)` |
| `--fg-dim` | `hsl(185 30% 30%)` |
| `--destructive` | `hsl(350 80% 55%)` |

139 measurements. Identical numerical contexts are grouped below; every context ID is included. RGB is displayed in 0–255 channels to three decimals; the JSON/CSV retain unrounded values. Unrounded ΔE decides acceptance. † marks a shortfall belonging to this single theme exception. Signatures are specified in verification.md; every shortfall uses two distinct signatures.

| Surface / Pair | Context(s) | Before RGB A; B | After RGB A; B | Before ΔE | After ΔE |
|---|---|---|---|---:|---:|
| memory: normal / over | fill | (0.000,233.750,255.000); (36.975,174.675,243.525) | (0.000,233.750,255.000); (0.000,136.000,204.000) | 14.40404073730409 | 25.295466866782746 |
| delete: unarmed / armed | ready/rest, ready/hover, ready/focus | (94.350,178.500,186.150); (232.050,48.450,79.050) | (76.500,170.000,178.500); (232.050,48.450,79.050) | 34.19818261757641 | 34.37953115956112 |
| delete: unarmed / armed | ready-exceeds/rest, ready-exceeds/hover, ready-exceeds/focus | (36.503,68.939,71.617); (84.698,23.422,34.132) | (30.256,65.964,68.939); (84.698,23.422,34.132) | 16.408197999576796 | 16.617971914349088 |
| key: optional-absent / required-missing | required/rest, optional/rest | (38.378,68.722,71.273); (36.975,174.675,243.525) | (29.452,52.785,54.697); (0.000,136.000,204.000) | 41.3508836007381 | 32.61282762915505 |
| key: optional-absent / present | required/rest | (38.378,68.722,71.273); (94.350,178.500,186.150) | (29.452,52.785,54.697); (76.500,170.000,178.500) | 39.08973543617644 | 39.249474049576584 |
| key: optional-absent / verified | required/rest | (38.378,68.722,71.273); (0.000,233.750,255.000) | (29.452,52.785,54.697); (0.000,233.750,255.000) | 54.864998719819546 | 63.516490332604576 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (36.975,174.675,243.525); (94.350,178.500,186.150) | (0.000,136.000,204.000); (76.500,170.000,178.500) | 13.513540821543312 | 16.175370890491763 |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (36.975,174.675,243.525); (0.000,233.750,255.000) | (0.000,136.000,204.000); (0.000,233.750,255.000) | 14.40404073730409 | 25.295466866782746 |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (94.350,178.500,186.150); (0.000,233.750,255.000) | (76.500,170.000,178.500); (0.000,233.750,255.000) | 13.427931019604726 | 15.713085462966294 |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (36.975,174.675,243.525) | (53.550,95.625,99.450); (0.000,136.000,204.000) | 21.78575194244601 | 21.79871330295108 |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (94.350,178.500,186.150) | (53.550,95.625,99.450); (76.500,170.000,178.500) | 16.28884750990673 | 26.390673594260058 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (71.400,127.500,132.600); (0.000,233.750,255.000) | (53.550,95.625,99.450); (0.000,233.750,255.000) | 28.837735721157593 | 41.48807053321351 |
| key: optional-absent / present | optional/rest | (38.378,68.722,71.273); (49.853,94.222,98.047) | (29.452,52.785,54.697); (40.928,89.972,94.222) | 7.90901489803421 | 11.20519917524077 † |
| key: optional-absent / verified | optional/rest | (38.378,68.722,71.273); (2.677,121.847,132.472) | (29.452,52.785,54.697); (2.677,121.847,132.472) | 16.70177044513478 | 21.305693912432318 |
| key: required-missing / present | optional/rest | (36.975,174.675,243.525); (49.853,94.222,98.047) | (0.000,136.000,204.000); (40.928,89.972,94.222) | 33.47067227577112 | 22.857687246613214 |
| key: required-missing / verified | optional/rest | (36.975,174.675,243.525); (2.677,121.847,132.472) | (0.000,136.000,204.000); (2.677,121.847,132.472) | 22.928891098979445 | 13.797779302542082 † |
| key: present / verified | optional/rest | (49.853,94.222,98.047); (2.677,121.847,132.472) | (40.928,89.972,94.222); (2.677,121.847,132.472) | 9.18874139605276 | 10.342645137480662 † |
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

All individual pair/context maxima and maximizing witnesses are in `vector-joint.json`. Maxima enumerate full factor domains (including irrelevant roots); the factor count is reported explicitly. They provide context and do not determine joint-exception acceptance. Historical opaque map-fill maxima remain in `map-fill-search.json`.
