# `color secondary tracked-window`

Syntax: `cutagent color secondary tracked-window [--clip VALUE] [--shape VALUE] [--pattern-center VALUE] [--comp VALUE]`

## Search terms

- create tracked power window
- track rectangle around subject
- add ellipse tracker secondary
- make moving grading window
- build Fusion window and tracker
- set up tracked localized grade
- follow object with rectangle mask
- add tracked oval color correction
- create window tracking scaffold
- place tracker pattern on object
- mask ColorCorrector with tracked window
- create motion-following secondary setup

## What it does

Create a tracked window secondary.

## Do not use when

Do not use this as proof of a finished tracked power window. Use `color window rectangle`/`ellipse` when window center, size or softness must be controlled; this wrapper exposes none of those. Use `color secondary subject-isolation` only for its fixed ellipse-named scaffold, not for AI segmentation. Use `color primary set` to set the correction the mask should gate. Avoid on a bespoke graph where global canonicalization/reordering is unacceptable.

## Preflight and readback

Before creation, place the playhead on a useful reference frame, inspect/export the entire Fusion graph, and record existing window/tracker order. Choose rectangle vs ellipse and a finite tracker pattern center, understanding that the center does not position the new window. Confirm the fixed centered half-frame window is an acceptable temporary shape and that a separate tracking/linking pass is planned. Dry-run validates syntax only.
Apply the intended ColorCorrector adjustment, inspect matte/output at multiple frames and check that existing masks were not reordered or newly activated. On failure after window creation, search for a partial leftover window because the two-step recipe is not atomic.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--shape` (optional, default: `"rectangle"`) — rectangle|ellipse
- `--pattern-center` (optional, default: `"0.5,0.5"`) — Tracker pattern center X,Y
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- No direction, range, timeout, completion or path verification exists in this command.
- `--pattern-center` controls only the tracking pattern.
- It does not move the rectangle/ellipse to that location.
- The output does not disclose that extra tracker state.
- Pattern center must contain two finite values, but there is no 0..1 bounds check.
- Only rectangle and ellipse are accepted.
- The command creates a neutral ColorCorrector if absent but does not set a visible grade.
- The returned final graph only proves the new names are active and structural invariants pass.
- It does not validate mask geometry, tracker inputs, linkage, analyzed motion or pixels.
- Dry-run is safely non-mutating and does not connect.
- Named clip matching selects the first case-insensitive name/basename across video tracks, with no track/time disambiguation.

## Examples

- `cutagent color secondary tracked-window --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
