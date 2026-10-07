# Clarification-1 Calibration Readback

2026-10-06, continuation from `7196634b`. The full panel report was read before
editing. The clarified like-part, opacity and backdrop pairing is implemented.
The core threshold remains 90%, mask minimum 16, opaque tolerance 1.0,
translucent tolerance 2.5, backdrop tolerance 1.0. No acceptance pair changed.

The named regeneration command exited 1 at non-vacuity after 74 Veil default
calibration samples, 28.056590208 seconds, with 18 media vectors / 27 condition
renders derived. No candidates or acceptance conditions rendered; the shipping
receipt was not replaced.

```text
Calibration non-vacuity failure Veil/key/optional/rest/present/verified:
required opaque pair, got translucent; effective opacities=0.5/0.5
```

Production `.key-row.optional { opacity: .5 }` applies to both samples at rest.
Their control-core backdrop difference is 2.6433254285953522e-14 deutan ΔE;
the painted difference is 0.01110400212806681. Thus this required pair exists
and passes as translucent, but cannot be an opaque pair under the clarification's
computed-opacity rule. A clarification question is pending; no reclassification
or production opacity change has been made.

| Group | Opaque Maximum | Translucent Maximum | Eligible Pairs | Skipped Pairs |
| --- | ---: | ---: | ---: | ---: |
| Memory | 0.000265589 | 0 | 1 | 0 |
| Delete | 0.006002891 | 0.012334577 | 8 | 0 |
| Key | 0.039586936 | 0.011104002 | 18 | 0 |
| Map | 0.074689175 | 0.416540489 | 34 | 20 |

All eligible Veil pairs pass their fixed tolerances. The archive retains every
skipped pair's reason, the effective opacities, data-map parts, core/control
means, and the four optional/rest painted/control witness PNGs. The mandatory
opaque clause stops before Gilded and Vector; no full regeneration or subsequent
proof is claimed. The earlier stop report remains historical.

Validation: `npm --prefix ui run check`, `node --check
ui/scripts/resolve-state-surfaces.mjs`, and `git diff --check` pass. The focused
acceptance suite requires a fresh completed receipt and remains deferred with
the rest of section 4.

Codex, GPT-6.
