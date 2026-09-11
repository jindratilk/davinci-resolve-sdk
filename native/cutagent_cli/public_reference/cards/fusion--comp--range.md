# `fusion comp range`

Syntax: `cutagent fusion comp range START END`

## Search terms

- set Fusion render range
- change comp start end frames
- limit Fusion preview range
- set composition work range
- trim Fusion render frames
- render only part of comp
- set Fusion local frame interval
- define comp playback range
- adjust Fusion composition bounds
- set render start and render end
- restrict Fusion render window

## What it does

Set composition render range.

## Do not use when

Use timeline trim/duration commands when the desired change is the timeline item's length or placement. Comp render range is local evaluation metadata and does not trim the clip.
Use keyframe or spline commands when animation keys must be moved, clipped, retimed, or deleted. Changing render bounds does not alter keyframes outside the range.
Use `fusion comp current` to inspect current render/global bounds before and after the mutation.
Range only sets attributes.
Use clip-scoped Fusion commands when the target comp must be selected by clip and index. This command can silently affect a different globally current comp.
Do not use global `--dry-run` for a safe preview.

## Preflight and readback

Compare the requested interval with `globalstart/globalend` and the target clip's local length. Require `start <= end` in agent logic; the command does not enforce it.
A successful message is insufficient because DaVinci Resolve can reject or normalize values without raising and the wrapper ignores the setter result.
Before play/render, confirm the range remains ordered and within the intended global interval. Restore the original range after temporary previews/tests and verify restoration.

## Public arguments and options

- `START` (required) — Start frame
- `END` (required) — End frame

## Boundaries and gotchas

- Values outside the global range can be silently rejected/normalized.
- The command does not clamp in application code, convert an inclusive/exclusive end convention, or derive clip duration.
- It does not modify global range.
- After setting render 5–20 and 30–10, global range stayed 0–47.
- It does not expose whether DaVinci Resolve rounded or converted values; CLI input is integer-only.
- Global `--dry-run` is mutating.
- The success response has no old/new range, comp name, changed flag, setter result, or verification status.
- Changing render range can affect subsequent comp play/render/cache operations even though it does not rewrite graph nodes or the timeline item.

## Stable public error codes

- `API_CALL_FAILED`
- `INVALID_OPTION`

## Examples

- `cutagent fusion comp range --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
