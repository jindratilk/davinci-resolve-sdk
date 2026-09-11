# `fusion keyframe clear`

Syntax: `cutagent fusion keyframe clear TOOL_NAME INPUT_NAME [--force]`

## Search terms

- clear Fusion keyframes
- remove all Fusion animation
- convert animated input to constant
- clear keyframes force
- keep current Fusion value
- machine confirmation keyframe clear
- remove BezierSpline animation
- restore Fusion constant
- destructive keyframe cleanup

## What it does

Clear all keyframes for an input (convert to constant value).

## Do not use when

Do not use this to remove one keyframe; it is all-or-nothing at the input level.
Do not run it without recording the full original animation and the active composition time/value.
Do not assume the retained constant will equal a desired default/original value.
Do not treat success as proof that keyframes existed or were removed. The wrapper ignores the final setter return and performs no list/readback.
Do not trust dry-run to verify comp, tool, input, current time, current value, or animation support.
Do not use it when active composition context is ambiguous; it has no clip, track, timeline-item, comp-index, or keep-frame option.

## Preflight and readback

Run dry-run and confirm the exact target. In machine mode, add force only after authorizing removal of every keyframe on that input.
For temporary testing, restore the original constant/animation, verify frame-specific values, keyframe list, complete tool list, and visual output, then return DaVinci Resolve to its original page.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Both arguments are required.
- `--force` / `-f` skips confirmation.
- Dry-run executes before confirmation and does not require force.
- The wrapper does not explicitly disconnect/delete a BezierSpline object.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent fusion keyframe clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
