# Clarification 2: Calibration Passes; the 320px Inventory Cannot Paint

The complete panel at `721ebe12` was read before editing. Continuation from
`76809378` applies only Clarification 2: optional key present/verified at rest
is a mandatory translucent pair. Required key rows and canvas/sidebar fills
remain mandatory opaque pairs. This implementation is checkpointed at
`02018234`. Core threshold 90%, opaque tolerance 1.0, translucent tolerance
2.5, backdrop tolerance 1.0 and mask floor 16 are unchanged.

## Full Regeneration Attempt

Executed the named command without filters or an adapter:

```sh
npm --prefix ui run resolve-state-surfaces
```

The emitted CSS produces 18 feature vectors and 27 phase-expanded condition
renders. All three full default calibrations pass: 74 samples per theme,
222 calibration samples total. [Calibration samples, all pairs, skips and
mandatory classifications](calibration.json) retain every referenced PNG
under [calibration](calibration/). Every mandatory optional/rest pair is
translucent, compares under the same-backdrop rule, and passes 2.5. Every
mandatory opaque pair passes 1.0. There is no calibration stop.

| Theme | Group | Opaque Maximum ΔE | Eligible Translucent Maximum ΔE | Skipped Pairs |
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

Input fingerprint: `db56270ace2481e24525c9a395897e59ae28cb0b401fd705cddecf48cacdcdc5`, 2254 files,
2095 fixture modules, Chromium 153.0.8010.12,
Playwright 1.63.0.

The acceptance inventory then stops after **477 renders /
80.661704500s**:

```text
Measurement failure w1-639/reduce/Vector/shipped/delete/ready/rest/unarmed/hsl(185 40% 55%): empty foreground mask
```

[Verbatim command output](regeneration.log), [named clip/readback](measurement-failure.json),
[incomplete receipt](incomplete-probe.json),
[painted PNG](measurement-failure-painted.png),
[control PNG](measurement-failure-control.png).
The two PNG files are byte-identical. The retained receipt is explicitly
`acceptanceComplete=false`; it never replaces the shipping acceptance receipt.

## Isolating Probe and Required Ruling

The new lowest integer width band is `w1-639`; its midpoint is 320px.
The real settings layout fixes the left rail at 240px. At this width the
nested `.lm-group` and `.lm-quants` compute to **0px width**; `.lm-quants`
retains `overflow:hidden`. The button's 11×11 SVG has a bounding box, but
its ancestor clips all its paint. The fresh clip is empty, not a low ΔE.

A browser probe on the same generated fixture, CSS, theme, width, DPR and
reduced-motion setting reproduces the zero-width clip. Twelve real Tab presses
reach the delete button. Clicking the body and moving the pointer off restores
rest semantics, but the ancestor remains 0px wide and the glyph remains
invisible. A scroll cannot widen that ancestor. [Probe source](clarification-2-width-probe.mjs),
[full before/after DOM geometry and hit readbacks](clarification-2-width-probe.log),
[before](width-320-before.png) and [after](width-320-after.png) full screenshots
were visually inspected. No synthetic focus, forced scroll width, substitute
viewport, removed comparison or product layout change was used.

The full-inventory rule and the 16-pixel floor cannot both pass at this required
representative. A clarification is requested: allow unpainted contexts to be
excluded per condition with capture evidence, or amend the viewport domain.
No interpretation is adopted without the ruling. Later items 7–14, the palette
search, remaining gates, PR update and push remain pending. The accepted
`721ebe12` shades and receipt are unchanged. `origin/main` currently has no
commits ahead of this branch; no rebase or stash was used.

`node --check ui/scripts/resolve-state-surfaces.mjs` passes. The TypeScript/design-sync
check is recorded separately in [check.log](check.log). Acceptance tests remain
deferred because full regeneration did not complete.

Codex, GPT-6.
