# `color tracker set-target`

Syntax: `cutagent color tracker set-target TRACKER_NAME [--center VALUE] [--clip VALUE] [--comp VALUE]`

## Search terms

- move tracker target
- set tracking point center
- reposition Fusion tracker
- change PatternCenter1
- place tracker on subject
- set tracker X Y
- move IntelliTrack point
- correct tracker start position
- target feature for motion tracking
- relocate Tracker tool point
- set normalized tracker coordinates

## What it does

Update a tracker target center.

## Do not use when

Use `color tracker add` when no Tracker exists. Do not use this as a readback command: returned coordinates are request echo, so inspect/export the Fusion comp to confirm persistence.

## Preflight and readback

Before running, identify the exact comp and Tracker with `color tracker list`, confirm whether it is active or orphaned, and inspect the frame where its target should be initialized.
Confirm all other points/keyframes are intentional. Then run the chosen tracking direction and inspect keyframes/visual motion across the needed range; render/frame-export samples to prove the tracked feature and downstream mask behave correctly. If the Tracker is orphaned, attach/repair it separately—moving its point does not activate it.

## Public arguments and options

- `TRACKER_NAME` (required) — Tracker tool name
- `--center` (optional, default: `"0.5,0.5"`) — Pattern center X,Y
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Coordinates only need to parse as two finite floats.
- `set-target` does not choose or move the playhead.
- It does not bind a geometric window to the Tracker.
- `tracker list` must be checked separately.
- Dry-run validates only strings, finite center and positive comp index.
- Duplicate clip names need prior target confirmation.

## Examples

- `cutagent color tracker set-target --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
