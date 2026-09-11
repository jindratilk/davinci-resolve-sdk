# `clip speed-ramp`

Syntax: `cutagent clip speed-ramp [--cut-at VALUE] [--out-frames VALUE] [--in-frames VALUE] [--peak-speed VALUE] [--curve VALUE] [--reverse-incoming] [--track VALUE] [--out-start-speed VALUE] [--out-end-speed VALUE] [--in-start-speed VALUE] [--in-end-speed VALUE] [--out-start-handle VALUE] [--out-end-handle VALUE] [--in-start-handle VALUE] [--in-end-handle VALUE] [--out-ease VALUE] [--in-ease VALUE] [--out-start-interp VALUE] [--out-end-interp VALUE] [--in-start-interp VALUE] [--in-end-interp VALUE] [--out-point VALUE] [--in-point VALUE] [--adjustment-blur] [--blur-frames VALUE] [--blur-track VALUE] [--blur-angle VALUE] [--blur-distance VALUE] [--blur-peak-opacity VALUE] [--blur-name VALUE]`

## Search terms

- speed ramp across a cut
- whip transition retime
- accelerate outgoing and decelerate incoming
- DaVinci Resolve S curve speed transition
- ramp to peak speed at edit point
- reverse incoming speed ramp
- add adjustment blur over speed ramp
- custom retime Bezier handles
- build timemap points around adjacent clips

## What it does

Apply a speed ramp across an adjacent cut.

## Do not use when

Use `clip speed` for one constant retime, standalone reverse/freeze for whole-item effects, and a transition/effect when no source handles exist for accelerated sampling. Do not enable adjustment blur merely to hide invalid retime frames; first prove the retime graph itself. Use explicit points/handles only from a measured reference because raw coordinates are source/output seconds after frame conversion, not intuitive percentages.

## Preflight and readback

Confirm a true adjacent cut on one video track, record both item IDs/bounds/source handles and linked audio, and export frames around the cut. Always dry-run with the final parameters.

## Public arguments and options

- `--cut-at` (optional, default: `"current"`) — Cut position: current playhead, frame, seconds, or timecode
- `--out-frames` (optional, default: `18`) — Outgoing ramp length in frames
- `--in-frames` (optional, default: `18`) — Incoming ramp length in frames
- `--peak-speed` (optional, default: `"6.5x"`) — Peak speed multiplier, e.g. 6.5x
- `--curve` (optional, default: `"sharp-s"`) — Curve shape: linear, normal-s, or sharp-s
- `--reverse-incoming` (optional, default: `false`) — Reverse the incoming clip while applying its ramp
- `--track` (optional, default: `0`) — Video track index (0 = auto-detect the adjacent cut)
- `--out-start-speed` (optional, default: `"1x"`) — Outgoing pre-ramp segment speed multiplier
- `--out-end-speed` (optional) — Outgoing end/ramp speed multiplier; defaults to --peak-speed
- `--in-start-speed` (optional) — Incoming start/ramp speed multiplier; defaults to --peak-speed
- `--in-end-speed` (optional, default: `"1x"`) — Incoming post-ramp segment speed multiplier
- `--out-start-handle` (optional) — Raw outgoing Bezier start handle, e.g. x=4f,y=4f
- `--out-end-handle` (optional) — Raw outgoing Bezier end handle, e.g. x=-4f,y=-26f
- `--in-start-handle` (optional) — Raw incoming Bezier start handle, e.g. x=4f,y=26f
- `--in-end-handle` (optional) — Raw incoming Bezier end handle, e.g. x=-4f,y=-4f
- `--out-ease` (optional, default: `"in-out"`) — Outgoing ramp easing: none, in, out, or in-out
- `--in-ease` (optional, default: `"in-out"`) — Incoming ramp easing: none, in, out, or in-out
- `--out-start-interp` (optional) — Raw DaVinci Resolve interp code for the outgoing ramp start point
- `--out-end-interp` (optional) — Raw DaVinci Resolve interp code for the outgoing ramp end point
- `--in-start-interp` (optional) — Raw DaVinci Resolve interp code for the incoming ramp start point
- `--in-end-interp` (optional) — Raw DaVinci Resolve interp code for the incoming ramp end point
- `--out-point` (optional, repeatable, default: `[]`) — Explicit outgoing timemap point: x=102f,y=102f,xOut=4f,yOut=26f; repeatable
- `--in-point` (optional, repeatable, default: `[]`) — Explicit incoming timemap point: x=0f,y=78f,xOut=4f,yOut=-26f; repeatable
- `--adjustment-blur/--no-adjustment-blur` (optional, default: `false`) — Insert a cut-centered Adjustment Clip with DirectionalBlur and opacity fade
- `--blur-frames` (optional, default: `8`) — Adjustment blur duration in frames
- `--blur-track` (optional, default: `0`) — Adjustment blur video track (0 = one above retime track)
- `--blur-angle` (optional, default: `0.0`) — Fusion DirectionalBlur angle
- `--blur-distance` (optional, default: `0.16`) — Fusion DirectionalBlur distance
- `--blur-peak-opacity` (optional, default: `1.0`) — Peak blur Blend/opacity from 0 to 1
- `--blur-name` (optional) — Adjustment blur clip name

## Boundaries and gotchas

- Auto track (`--track 0`) can be ambiguous when cuts align on multiple video tracks.

## Examples

- `cutagent clip speed-ramp --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
