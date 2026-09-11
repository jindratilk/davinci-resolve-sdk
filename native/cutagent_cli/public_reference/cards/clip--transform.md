# `clip transform`

Syntax: `cutagent clip transform [NAME] [--batch-file VALUE] [--zoom-x VALUE] [--zoom-y VALUE] [--zoom VALUE] [--position-x VALUE] [--position-y VALUE] [--rotation VALUE] [--anchor-x VALUE] [--anchor-y VALUE] [--pitch VALUE] [--yaw VALUE] [--flip-x] [--flip-y] [--opacity VALUE] [--crop-left VALUE] [--crop-right VALUE] [--crop-top VALUE] [--crop-bottom VALUE] [--distortion VALUE] [--dynamic-zoom-ease VALUE] [--reset]`

## Search terms

- move scale rotate timeline clip
- set clip zoom and position
- crop or flip a shot
- change clip opacity
- reset Inspector transform
- batch transform timeline items
- set pan tilt anchor pitch yaw

## What it does

Check clip transform properties.

## Do not use when

Use `clip keyframe add` for animated Edit Inspector properties, a correctly connected Fusion Transform workflow for node-based motion, and `clip composite` when changing blend mode rather than geometry.

## Preflight and readback

After mutation, run the getter, compare each requested property and type, and export/inspect a representative frame. After `--reset`, verify all intended defaults and separately inspect fields the reset does not touch.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--batch-file` (optional) — JSON array/object of clip transform entries to apply in one DaVinci Resolve session
- `--zoom-x` (optional)
- `--zoom-y` (optional)
- `--zoom` (optional) — Set both zoom X and Y
- `--position-x/--pan` (optional)
- `--position-y/--tilt` (optional)
- `--rotation` (optional)
- `--anchor-x` (optional)
- `--anchor-y` (optional)
- `--pitch` (optional)
- `--yaw` (optional)
- `--flip-x/--no-flip-x` (optional)
- `--flip-y/--no-flip-y` (optional)
- `--opacity` (optional) — 0.0 to 100.0
- `--crop-left` (optional)
- `--crop-right` (optional)
- `--crop-top` (optional)
- `--crop-bottom` (optional)
- `--distortion` (optional)
- `--dynamic-zoom-ease` (optional) — linear|in|out|inout
- `--reset` (optional, default: `false`) — Reset all transforms

## Boundaries and gotchas

- Single-item global `--dry-run` is broken and mutating.
- Batch dry-run is implemented separately and only returns a plan.
- `--zoom` is applied first; a simultaneous `--zoom-x` or `--zoom-y` silently overrides only that axis.
- Batch entries must provide both track and record frame or neither.

## Examples

- `cutagent clip transform --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
