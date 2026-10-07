# STOP-REPORT: Clarification 3 Has Two Different Upper-Band Representatives

2026-10-06. Resumed from `8a528239`; the nearest-edge implementation is
checkpointed at `48244fc2`. The complete panel report at `721ebe12`, the
original order, amendments and round-4 order with all eight clarifications
were read before editing. The accepted measurement/calibration work stays.

## The Contradiction

Clarification 3 requires “a band's representative is the band edge nearest
the default viewport (1200 × 900)” and “for bands above it the band's minimum”.
It also explicitly names these shipped representatives:

```text
639, 760, 767, 1023, 1100, 1200, 1280, 1535, 1536
```

The actual emitted CSS has `(max-width: 1280px)`, `(min-width: 1280px)`
and `(min-width: 1536px)`. Its adjacent bands are the singleton 1280,
**1281–1535**, and 1536+. For 1281–1535 the minimum and nearest edge are
**1281**, 81px from 1200. The explicitly named **1535** is the maximum,
335px from 1200. Both instructions cannot hold for this band.

The implemented nearest-edge rule produces:

```text
639, 760, 767, 1023, 1100, 1200, 1280, 1281, 1536
18 feature vectors; 27 phase-expanded condition renders
```

[Parsed inventory](media.json) records every prelude, vector and condition.
A [native Chromium endpoint probe](band-witness.json), with network aborted,
confirms that 1281 and 1535 satisfy the same prelude set, while 1280 and 1536
are in distinct bands. This is a specification conflict over the representative,
not a prelude-coverage or layout failure.

The standing common order says: “If the order's premise turns out to be false,
write a stop-report instead of improvising.” No 1535 exception to the nearest-edge
rule, substitute viewport, skipped context or threshold change was adopted.
A ruling must choose **1281 under the nearest-edge rule**, or **1535 as an
explicit exception for this band**. The 18-vector/27-render count is unchanged.

## Regeneration and Calibration

The literal command `npm --prefix ui run resolve-state-surfaces` was started
without filters. Every default calibration passed: 74 samples per theme,
**222 calibration samples**, with the prescribed 90% core threshold, 16-pixel
mask floor and 1.0/2.5/1.0 opaque/translucent/backdrop tolerances unchanged.
[Full calibration record](calibration.json) preserves pairs, mandatory
classifications, skipped reasons, mask/core sizes and histogram audit buckets;
every referenced painted/control PNG is archived under [calibration](calibration/).

| Theme | Group | Opaque Maximum ΔE | Translucent Maximum ΔE | Skipped Pairs |
| --- | --- | ---: | ---: | ---: |
| Veil | memory | 0.000265588751 | 0.000000000000 | 0 |
| Veil | delete | 0.006002891112 | 0.012334576619 | 0 |
| Veil | key | 0.039586935763 | 0.011104002128 | 0 |
| Veil | map | 0.074689175102 | 0.416540489219 | 20 |
| Gilded | memory | 0.000266201443 | 0.000000000000 | 0 |
| Gilded | delete | 0.008785869899 | 0.007902349658 | 0 |
| Gilded | key | 0.036896147109 | 0.013172053989 | 0 |
| Gilded | map | 0.071159088576 | 0.444708084503 | 19 |
| Vector | memory | 0.000311149033 | 0.000000000000 | 0 |
| Vector | delete | 0.029118582413 | 0.021526638520 | 0 |
| Vector | key | 0.040124408459 | 0.014057713075 | 0 |
| Vector | map | 0.080534555455 | 0.343203203741 | 19 |

Capture progressed through the low-width conditions without the earlier 320px
clipping failure. When the independent representative-list assertion exposed
the 1281/1535 conflict, Codex deliberately terminated only this command's own
Chromium browser. This caused the recorded `Target page, context or browser
has been closed` exception. It is an intentional stop, **not a spontaneous
measurement failure**. The command and its browser processes have exited.

[Verbatim regeneration output](regeneration.log):

```text
Incomplete painted probe: renders=26896; wall=530.131s; acceptanceComplete=false
```

[Interrupted-capture record](interrupted-capture.json) retains the input
fingerprint, render count, wall time, initialized condition list, failure
and unchanged shipping-file hashes. The incomplete raw probe remains at
`scratchpad/777-S2/after-review-r5/capture/incomplete-probe.json`; it did not
replace the acceptance receipt. Input fingerprint:
`30c0def2055fed5facd01e4c3c15eae585af0e38bd32b679f9b8e227f351172b`.

## Checks, Checkpoints and Deferred Work

- `media.mjs` implements the nearest edge in place of the midpoint. The README
  describes the actual rule and explicitly records the unresolved 1535 value.
- `node --check ui/scripts/state-surfaces/media.mjs`: exit 0, no output.
- `git diff --check`: exit 0, no output.
- `npm --prefix ui run check`: exit 0; [verbatim output](check.log):

```text
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync

> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

Both `ui/client/src/index.css` and `ui/client/src/state-surfaces.resolved.json`
are byte-identical to `721ebe12`, independently compared with `git show` and
hashed in the interruption record. No palette or acceptance claim was refreshed.
The full regeneration did not finish. The focused acceptance run, search,
shipped token changes, items 7–14, plants, offline/owner-target/reachability
proofs, final merge, PR-body update and push remain pending. No rebase or stash
was used. `git fetch origin` found zero commits in `HEAD..origin/main`.
The partial run is preserved; it is not a passed gate.

Codex, GPT-6.
