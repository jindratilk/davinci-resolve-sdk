# `multicam timeline-create`

Syntax: `cutagent multicam timeline-create [--job VALUE] [--job-json VALUE] [--cleanup-stale] [--replace-existing]`

## Search terms

- create multicam target timeline
- structured multicam job timeline
- cleanup stale multicam rows
- replace existing multicam alias
- default multicam placement
- infer multicam timeline duration
- six angle multicam timeline

## What it does

Create a multicam timeline.

## Do not use when

Do not rely on dry-run to detect name collisions, missing Media Pool sources, a non-Disk project, unsupported switch-family data, or insufficient source duration.
Do not omit usable duration evidence for the two-to-four-logical-angle path.
Inspect every angle and render the resulting timeline. For repeated-angle sources, render frames on both sides of every source boundary.

## Preflight and readback

Run dry-run and verify its normalized target/name/order/cleanup summary.
Verify the new Media Pool multicam, exact angle bindings, source timing, target timeline, single default placement, duration, MediaRef, and start timecode.
Open the timeline and multicam in DaVinci Resolve, exercise angle switching, inspect audio/video sync, and render representative frames before accepting success.

## Public arguments and options

- `--job` (optional) — Path to a structured multicam job JSON file
- `--job-json` (optional) — Inline structured multicam job JSON
- `--cleanup-stale` (optional, default: `false`) — Remove DB-only stale target rows for this multicam/timeline name before creating
- `--replace-existing` (optional, default: `false`) — Alias for --cleanup-stale; live visible targets still fail

## Boundaries and gotchas

- Exactly one of `--job` or `--job-json` is required.
- `--cleanup-stale` and `--replace-existing` produce the same boolean behavior.
- No separate `--force` option is exposed.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam timeline-create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
