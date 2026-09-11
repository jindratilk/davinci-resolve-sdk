# `timeline layout free-stack`

Syntax: `cutagent timeline layout free-stack [--timeline VALUE] [--track-type VALUE] --start-frame VALUE [--end-frame VALUE] [--duration VALUE] [--candidate-stacks VALUE] [--stack-size VALUE] [--min-track VALUE] [--max-track VALUE] [--padding VALUE] [--shift] [--ensure-tracks] [--allow-missing-tracks] [--all-candidates]`

## Search terms

- find free timeline tracks
- plan overlay track stack
- collision-free track layout
- shift layout after blockers
- candidate video track stacks
- reserve timeline range
- missing track planning
- layered timeline placement

## What it does

Plan a layered timeline layout.

## Do not use when

Do not use the result as a reservation or atomic placement guarantee. The command only observes current state; another edit can occupy the range immediately afterward.
Do not blindly execute a shifted suggestion. The shifted range is calculated from blockers found around the original request and is not rescanned for collisions with later items.
Do not expect `--ensure-tracks` to create tracks or `--all-candidates` to change diagnostic inclusion. Both options are currently echoed in output but do not alter planning behavior.

## Preflight and readback

Before execution, confirm the intended timeline, track type, FPS/start frame, candidate stack order, padding, and whether missing tracks may be treated as plannable. Prefer explicit candidate stacks or an explicit `--max-track` when targeting a named timeline.
Immediately recheck the selected range before any later insertion, especially for `shifted: true`, and create required tracks through a separate command before placing media.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track-type` (optional, default: `"video"`) — Track type: video, audio, or subtitle
- `--start-frame/--record-start` (required) — Timeline-relative record ref; 0f is timeline start
- `--end-frame/--record-end` (optional) — Timeline-relative record ref; use duration for relative length
- `--duration` (optional) — Duration in frames, seconds, or timecode
- `--candidate-stacks` (optional) — JSON array of candidate track stacks, e.g. [[4,5],[6,7]]
- `--stack-size` (optional) — Generate contiguous candidate stacks of this size
- `--min-track` (optional, default: `1`) — First track for generated contiguous stacks
- `--max-track` (optional) — Last track for generated contiguous stacks; defaults to current track count
- `--padding` (optional, default: `"0f"`) — Collision padding in frames, seconds, or timecode
- `--shift/--no-shift` (optional, default: `true`) — Suggest and select the nearest shifted start when no stack is free
- `--ensure-tracks/--no-ensure-tracks` (optional, default: `false`) — Report whether missing tracks would need creation; does not mutate
- `--allow-missing-tracks` (optional, default: `false`) — Treat tracks above the current count as plannable but requiring creation
- `--all-candidates` (optional, default: `false`) — Include detailed candidate diagnostics

## Boundaries and gotchas

- `--timeline NAME` switches that project timeline current.
- Start is required through `--start-frame` or `--record-start`.
- Supply exactly one of `--end-frame`/`--record-end` or `--duration`.
- Duration must resolve above zero because end must be strictly after start.
- Padding expands the collision window on both sides of the requested range.
- Items whose bounds throw or cannot convert to integers are silently skipped.
- Explicit track indices must be positive and unique within each stack.
- An explicit `--candidate-stacks` value takes precedence over generated-stack behavior.
- `--min-track` and `--max-track` are still validated even when explicit stacks are supplied.
- If `--max-track` is omitted, the command initially uses the current timeline's reported track count.
- Generated candidates for a named timeline can therefore be based on the wrong timeline's track count unless `--max-track` is explicit.
- `--ensure-tracks` does not change the planner, create tracks, or add a separate preflight; it is only copied into `options`.
- `--all-candidates` is only copied into `options`; false does not suppress the candidate list.
- `--shift` defaults on.
- The planner does not rescan the suggested shifted range, so a later, initially nonblocking item may collide with it.
- With `--no-shift`, the best suggestion is still returned but `selected` is null and `ready` is false.
- Missing-only candidates have no blocking end and therefore generate no shift suggestion.
- The result does not inspect track locks, enabled state, linked items, transitions, compositing interactions, clip content, or future edits.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline layout free-stack --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
