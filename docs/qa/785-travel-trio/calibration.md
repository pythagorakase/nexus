# Travel calibration, 785-S5

Sources fetched October 8, 2026. Speeds are km/h and detours multiply geodesic
distance. Source substitutions follow the frozen order: retain a value when
the designated source cannot be fetched or does not state the required figure.
These are broad estimates, not route-specific schedules or journey guarantees.

| Mode | Old speed | New speed | Source and result |
|---|---:|---:|---|
| walking |5.0|5.0|Bohannon (1997) tables 1/4 give age/sex group sizes and means, but no stated all-adult mean; retained.|
| vehicle |45.0|45.0|FHWA 2017 NHTS table 6b gives adjusted all-purpose mean length 10.5 mi; the report gives commute durations, not the required all-purpose duration; retained.|
| rail |75.0|47.8|FTA 2024 NTST v1.2 p.103 states “CR (29.7 miles per hour)”; 29.7×1.609344=47.7975168, rounded to 47.8.|
| water |25.0|25.0|The same report's exhibit 10.8 plots ferry speed with no numeric value label; its 11.3% label is a change since 2014, not a speed. Retained rather than assigning false precision from bar length.|
| air |450.0|450.0|No fetched BTS or ICAO publication stated a qualifying domestic scheduled-flight average block speed. Retained.|
| covert |3.5|2.4|US Army FM 21-18 (1990), appendix A-5: “DAY ... 2.4 kph” under CROSS COUNTRY.|
| mixed |25.0|25.0|FHWA table 5b gives adjusted all-purpose person-trip length 11.6 mi, but no matching duration; retained.|

Vehicle detour changes 1.25→1.20. Ballou, Rahardja and Sakai (2002), table 1 p.846,
reports “United States 299 1.20 0.17”: 299 sampled pairs, mean 1.20, standard
deviation 0.17, excluding Alaska/Hawaii. This is an inter-city road factor;
the paper does not calibrate city-grid, rail, air or water travel. Every other
detour stays unchanged: walking 1.35, rail 1.15, water 1.40, air 1.05, covert 1.80,
mixed 1.40. The source and retention reasons are also beside the TOML tables.

## Source links and retrieval limits

- [Bohannon (1997) publisher](https://doi.org/10.1093/ageing/26.1.15),
  [author-uploaded full text](https://www.researchgate.net/publication/14075875_Comfortable_and_maximum_walking_speed_of_adults_aged_20-79_years_Reference_values_and_determinants).
  Publisher retrieval failed; the author-uploaded text exposes tables 1/4.
  The paper reports subgroup means. No mean from a different study was used.
- [FM21-18 primary Army manual, university ROTC mirror](https://www.elon.edu/assets/docs/rotc/FM%2021-18%20Foot%20Marches.pdf).
  The official Benning copy timed out; the mirror's manual and printed A-5 were
  fetched and read. The cross-country rate is a calibration proxy for covert
  travel selected by the work order; it is not a measured stealth speed.
- [FHWA 2017 NHTS Summary of Travel Trends](https://www.fhwa.dot.gov/policyinformation/documents/2017_nhts_summary_travel_trends.pdf),
  revised 2022 adjusted estimates, printed pp.17/20. Table 27's durations apply to
  commuting, so they cannot supply either all-trip denominator. Daily-driving
  time and trip totals have different populations and were not divided.
- [FTA latest NTST listing](https://www.transit.dot.gov/ntd/national-transit-summaries-and-trends-ntst),
  [2024 NTST v1.2](https://www.transit.dot.gov/sites/fta.dot.gov/files/2026-04/2024%20National%20Transit%20Summaries%20and%20Trends_1.2.pdf).
  FTA defines average revenue speed as actual revenue miles divided by actual
  revenue hours, including dwell. The fetched report provides the commuter
  rail number in prose. The ferry chart supplies no precise number. Attempts
  to fetch the underlying 2024 Service workbook also failed (HTTP 403); no
  older report or differently scoped aggregate was substituted.
- [Ballou et al. publisher](https://www.sciencedirect.com/science/article/pii/S0965856401000441),
  [full primary article mirror](https://www.scribd.com/document/845655933/Ronald-H-Ballou-Road-travel).
  Publisher retrieval failed; the six-page article's table 1 was read through
  the public mirror. Its bibliographic identity and pagination agree with
  DOI 10.1016/S0965-8564(01)00044-1. The site's generated description was not
  used as evidence.
- Air searches covered BTS/ROSA and ICAO domestic block speed. Retrieved
  materials defined block speed or reported individual historical aircraft,
  not the specified scheduled domestic aggregate. No new value is asserted.

## Pinned real-Earth samples

On October 8 a PostgreSQL transaction against NEXUS_template was explicitly
read-only and repeatable-read; `SHOW transaction_read_only` returned `on`.
Distances were recomputed with
`ST_Distance(ST_SetSRID(ST_MakePoint(lon1,lat1),4326)::geography,
ST_SetSRID(ST_MakePoint(lon2,lat2),4326)::geography)`.
Coordinates and rounded metres match the frozen order and test comments.
Minutes use distance×detour÷speed; tests pin within 0.01 minute.

|Mode|Route|Geodesic metres|Before minutes|After minutes|
|---|---|---:|---:|---:|
| walking | Times Square to Bethesda Terrace | 2148.2 | 34.80 | 34.80 |
| covert | Times Square to Bethesda Terrace | 2148.2 | 66.29 | 96.67 |
| vehicle | Grand Central to JFK | 20885.6 | 34.81 | 33.42 |
| rail | Penn Station to 30th Street | 134099.8 | 123.37 | 193.57 |
| water | Whitehall to St. George | 8184.9 | 27.50 | 27.50 |
| air | JFK to LAX | 3983079.7 | 557.63 | 557.63 |
| mixed | Borough Hall to Times Square | 7251.7 | 24.37 | 24.37 |

## Reference corpus check

The same read-only transaction policy was used on `ref_codex_bakeoff_2026_07`.
111 narrative chunks and 16 registered places were scanned. Search covered
whole-word second/minute/hour/day/week variants in narrative text; 289 timing
mentions across 99 chunks were inspected in context, excluding ordinal uses
such as “second rider”. Registered places and junction references were read
alongside those passages. No complete narrated journey had both unambiguous
registered endpoints and an explicit elapsed travel duration, so the corpus
supplies no further change and no defensible before/after journey pair.

Near cases are retained here to make that judgment reviewable:

|Chunk|Quoted timing|Why no journey estimate|
|---:|---|---|
|31|“Dry bay seven minutes.”|A remaining access window, not travel time between two places.|
|49|“Estimated arrival at Pylon Three’s sublevel return: eleven minutes.”|A remaining ETA from an unstated current skiff position. Market basin and Pylon Three sublevel are not two uniquely resolved endpoints; nearby registered Pylon places are IDs 7/8.|
|64|“Four hundred meters. Against return flow.” / “Eleven-minute cycle.”|The duration is a pump cycle, not the journey time.|
|83|“For the first ten minutes, the ugliness of the route is its protection.”|A partial journey segment; the ending point of those ten minutes is unregistered.|
|134|“Two minutes ... Past the blue pillars.”|The blue pillars are not a registered destination; the speaker describes a future handoff.|
|139–142|“RECONNECT DEFERRED” countdowns|A device reconnect timer decreases while travel and stops occur; it is not a stated full journey duration.|

Local retrieval products, query output and the candidate excerpts are under
`temp/orders_2026_10_08_codex/785-sources` in the main checkout. They are not
runtime inputs. Automated sample pins are in
tests/test_config/test_orrery_travel_settings.py; configured override behavior
remains covered by tests/test_orrery/test_routing.py.

## Focused verification

The two calibration/configuration test files passed: 22 tests, 5 inherited
OpenTelemetry warnings. The secret-store guard was active and denied nexus-api.
Black and flake8 passed both files. Mypy passed both files with no issues; no PostgreSQL was needed for these pure estimate assertions.

Issue785 before/after notice: https://github.com/pythagorakase/nexus/issues/785#issuecomment-6063841210

Codex — GPT-6
