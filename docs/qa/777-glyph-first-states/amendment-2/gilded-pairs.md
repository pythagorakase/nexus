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
| key: optional-absent / required-missing | required/rest, optional/rest | (75.225,66.555,44.625); (172.125,114.750,57.375) | (58.650,52.148,35.700); (172.125,114.750,57.375) | 26.499836873763076 | 31.478439290789392 |
| key: optional-absent / present | required/rest | (75.225,66.555,44.625); (181.560,153.816,83.640) | (58.650,52.148,35.700); (209.100,191.760,147.900) | 37.75836766671828 | 56.821216360613214 |
| key: optional-absent / verified | required/rest | (75.225,66.555,44.625); (208.539,158.282,31.161) | (58.650,52.148,35.700); (208.539,158.282,31.161) | 44.69332355199398 | 49.846448287962716 |
| key: required-missing / present | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (181.560,153.816,83.640) | (172.125,114.750,57.375); (209.100,191.760,147.900) | 9.20305994887555 | 20.063656851921923 |
| key: required-missing / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (172.125,114.750,57.375); (208.539,158.282,31.161) | (172.125,114.750,57.375); (208.539,158.282,31.161) | 14.337990382173535 | 14.337990382173535 † |
| key: present / verified | required/rest, required/hover, required/focus, optional/hover, optional/focus | (181.560,153.816,83.640); (208.539,158.282,31.161) | (209.100,191.760,147.900); (208.539,158.282,31.161) | 8.084904016113446 | 14.889609692629227 † |
| key: optional-absent / required-missing | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (172.125,114.750,57.375) | (99.450,86.445,53.550); (172.125,114.750,57.375) | 7.72892192098335 | 18.784598711480943 |
| key: optional-absent / present | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (181.560,153.816,83.640) | (99.450,86.445,53.550); (209.100,191.760,147.900) | 15.32055288939221 | 36.941089895489256 |
| key: optional-absent / verified | required/hover, required/focus, optional/hover, optional/focus | (132.600,115.260,71.400); (208.539,158.282,31.161) | (99.450,86.445,53.550); (208.539,158.282,31.161) | 21.598012943420677 | 34.346574359376135 |
| key: optional-absent / present | optional/rest | (75.225,66.555,44.625); (99.705,85.833,50.745) | (58.650,52.148,35.700); (113.475,104.805,82.875) | 8.182166780829279 | 18.343538747812936 |
| key: optional-absent / verified | optional/rest | (75.225,66.555,44.625); (113.194,88.066,24.505) | (58.650,52.148,35.700); (113.194,88.066,24.505) | 13.909040134210612 | 18.62936373084396 |
| key: required-missing / present | optional/rest | (172.125,114.750,57.375); (99.705,85.833,50.745) | (172.125,114.750,57.375); (113.475,104.805,82.875) | 18.621349381197312 | 16.00519085195528 |
| key: required-missing / verified | optional/rest | (172.125,114.750,57.375); (113.194,88.066,24.505) | (172.125,114.750,57.375); (113.194,88.066,24.505) | 15.059450129901082 | 15.059450129901082 |
| key: present / verified | optional/rest | (99.705,85.833,50.745); (113.194,88.066,24.505) | (113.475,104.805,82.875); (113.194,88.066,24.505) | 6.8760186056184835 | 12.158313227019862 † |
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
