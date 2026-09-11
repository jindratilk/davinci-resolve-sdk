# `clip keyframe get`

Syntax: `cutagent clip keyframe get [PROPERTY_NAME] [--clip VALUE]`

## Search terms

- list clip Inspector keyframes
- inspect opacity keyframes
- get timeline item motion animation
- diagnose animated pan tilt crop
- inspect keyframe interpolation values
- verify keyframe add or delete
- show record-frame keyframes

## What it does

Read keyframes.

## Do not use when

Use `clip info`, `transform`, or `properties` for current static Inspector values; an empty keyframe list does not report the held/base value. Use Fusion tool/keyframe commands for animation inside a Fusion composition, Fairlight automation commands for track automation, and retime/speed-ramp commands for speed points. Use `clip keyframe add/delete/set-interpolation` only when mutation is intended; this command is read-only.

## Public arguments and options

- `PROPERTY_NAME` (optional) — Property name (all known properties when omitted)
- `--clip` (optional) — Clip name (current clip when omitted)

## Examples

- `cutagent clip keyframe get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
