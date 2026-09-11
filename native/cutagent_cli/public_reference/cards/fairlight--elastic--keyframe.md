# `fairlight elastic keyframe`

Syntax: `cutagent fairlight elastic keyframe [--clip VALUE] [--at VALUE] [--ratio VALUE] [--time-point VALUE]`

## Search terms

- stretch audio clip without ripple
- lengthen dialogue with Elastic Wave
- time-compress audio clip
- add Fairlight timing point
- map output time to source time
- create audio retime keyframes
- set Elastic Wave segment speed
- preserve pitch while stretching audio
- change audio duration by ratio
- create curved Elastic timing point

## What it does

Runs the public `fairlight elastic keyframe` CutAgent command.

## Do not use when

Do not use this command only to choose Voice, General Purpose, or Varispeed; use `fairlight elastic enable`. Do not use `--time-point` to change the overall duration: its final output and source endpoints must both equal the current clip end; use `--ratio` for whole-clip duration change. Do not use this audio command for video speed changes; use the clip speed/retime command family. Do not request both `--ratio` and `--time-point`; validation rejects the combination.

## Preflight and readback

Record start, duration, following clip positions, algorithm state, old timemap, and source range. Checkpoint a disposable project and use dry-run to confirm route. After a ratio edit, verify new duration, non-default timemap, unchanged starts of following clips, and whether pitch correction actually applied. After explicit points, require exact decoded `x/y/handle/interp` values and unchanged duration. Render or audibly inspect any production edit.

## Public arguments and options

- `--clip` (optional) — Timeline clip name or item id
- `--at` (optional) — Timeline timecode/frame/seconds for clip selection
- `--ratio` (optional) — Requested whole-clip stretch ratio; 1.25 lengthens by 25%
- `--time-point/--point` (optional, repeatable, default: `[]`) — Explicit segment Elastic output-to-source point, e.g. x=5s,y=4s; optional x_in/y_in/x_out/y_out/interp raw handle fields; repeatable.

## Boundaries and gotchas

- `--time-point` values accept seconds, frames, or timecode, but all output `x` values must be strictly increasing, source `y` values must never move backward, and both must remain inside the current duration.
- It automatically supplies identity endpoints only when absent and then requires the final point to be identity at clip end.
- Do not layer modes casually without re-reading source extent and rendering.

## Examples

- `cutagent fairlight elastic keyframe --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
