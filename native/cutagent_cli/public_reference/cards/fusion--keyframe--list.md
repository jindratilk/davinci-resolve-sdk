# `fusion keyframe list`

Syntax: `cutagent fusion keyframe list TOOL_NAME INPUT_NAME`

## Search terms

- list Fusion keyframes
- inspect Fusion animation
- keyframe frame value readback
- no keyframes detected warning
- Fusion keyframe detection limits
- active composition keyframes
- verify Fusion animation
- dry-run keyframe list connects

## What it does

List keyframes for an input.

## Do not use when

Do not treat the warning as definitive proof that the input has no animation.
Do not treat detected rows as complete without comparing the Fusion UI, direct frame-specific input reads, and representative render state.
Do not expect global dry-run to avoid DaVinci Resolve access.
Do not use this when the active composition is ambiguous; no clip, track, timeline-item, or composition-index selector is available.
Do not use it to list every animated input on a tool or comp.
Do not rely on it as the only verification for `fusion keyframe add/set`.

## Preflight and readback

Before listing, open the intended Fusion composition and confirm the timeline, clip, tool name, and input ID with tool-list/input-list commands.
Run the list without assuming dry-run isolation. Capture whether the response contains row data or a warning.
For each reported frame, use `fusion tool get TOOL INPUT --time FRAME`; also sample at least one non-keyframe frame and compare expected values.
When the list is empty but values differ by frame, treat detection as incomplete. When the list is empty and all values are identical, treat the input as constant unless stronger evidence says otherwise.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name

## Boundaries and gotchas

- Both arguments are required; there are no command-specific options.
- There is no dry-run conditional.
- A warning does not distinguish no animation from unsupported/incomplete detection.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion keyframe list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
