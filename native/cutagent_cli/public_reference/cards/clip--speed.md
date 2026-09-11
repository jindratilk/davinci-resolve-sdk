# `clip speed`

Syntax: `cutagent clip speed [NAME] [--set VALUE] [--speed-percent VALUE] [--fps VALUE] [--duration VALUE] [--ripple-timeline] [--reverse-speed] [--freeze-frame] [--pitch-correction] [--keyframes VALUE] [--at VALUE]`

## Search terms

- change clip speed
- set video to 200 percent
- speed up or slow down shot
- set clip duration by retime
- reverse speed or freeze frame
- ripple timeline after speed change
- inspect current retime state
- preserve audio pitch when retiming
- set frames per second playback

## What it does

Check clip speed.

## Do not use when

Do not use getter with `--at`: current validation allows `--at` only alongside a mutation.

## Preflight and readback

Run getter by unique clip name, retain all decoded durations/timemap and item/neighbor positions, then dry-run the exact mutation with `--at`. Check desired new duration and whether ripple is intended. For ripple, inspect every shifted downstream row on all involved tracks and transitions/gaps at the new boundary.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--set/--multiplier` (optional) — Speed multiplier (e.g., 2.0 for 2x)
- `--speed-percent/--percent` (optional) — GUI Speed value in percent (e.g., 200 for 2x)
- `--fps/--frames-per-second` (optional) — GUI Frames per Second value
- `--duration` (optional) — GUI Duration value, e.g. 00:01:23:00 or 120f
- `--ripple-timeline/--no-ripple-timeline` (optional, default: `false`) — Ripple downstream timeline items after the speed change
- `--reverse-speed` (optional, default: `false`) — Apply the GUI Reverse Speed option
- `--freeze-frame` (optional, default: `false`) — Apply the GUI Freeze Frame option
- `--pitch-correction/--no-pitch-correction` (optional) — Set the GUI Pitch Correction option when the Disk DB stores clip speed state
- `--keyframes` (optional, default: `"maintain-timing"`) — GUI keyframe timing mode: maintain-timing or stretch-to-fit
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- Dry-run is correctly non-mutating on the Disk route.
- Video-only readback returns null.

## Examples

- `cutagent clip speed --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
