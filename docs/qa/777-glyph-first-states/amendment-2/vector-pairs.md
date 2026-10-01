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
