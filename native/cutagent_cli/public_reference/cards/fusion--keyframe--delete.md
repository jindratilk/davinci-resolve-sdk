# `fusion keyframe delete`

Syntax: `cutagent fusion keyframe delete TOOL_NAME INPUT_NAME FRAME`

## Search terms

- fusion keyframe delete
- Remove one Fusion spline keyframe while preserving the remaining animation.
- fusion keyframe delete help
- fusion keyframe delete command

## What it does

Remove one Fusion spline keyframe while preserving the remaining animation.

## Do not use when

Do not use it to remove all animation; use `fusion keyframe clear --force` for that broader operation.
Do not use it when the active composition, tool, or input is ambiguous. The command has no clip, track, or composition selector.
Do not rely on dry-run to confirm the target because it does not inspect the active composition or target keyframe.

## Preflight and readback

After success, run `fusion keyframe list` again and sample the deleted frame plus neighboring keyed frames with `fusion tool get TOOL INPUT --time FRAME -j`. For visible animation, export representative frames or render output.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `FRAME` (required) — Frame number

## Boundaries and gotchas

- The command does not fall back to `clear`, so it never intentionally removes unrelated keyframes.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion keyframe delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
