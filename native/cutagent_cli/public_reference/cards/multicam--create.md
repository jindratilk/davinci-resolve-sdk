# `multicam create`

Syntax: `cutagent multicam create [--job VALUE] [--job-json VALUE] [--angle VALUE] [--timeline-name VALUE] [--multicam-name VALUE] [--sync-mode VALUE] [--cleanup-stale] [--replace-existing]`

## Search terms

- structured multicam job
- multicam angle sources
- stale multicam cleanup
- multicam dry-run plan

## What it does

Create a multicam clip in the media pool.

## Do not use when

Do not use this on PostgreSQL/cloud/non-Disk project databases.
Do not use ambiguous clip names.
Do not expect this command to create/materialize the named timeline or apply switch segments. Use `multicam timeline-create` or the later switch workflow as appropriate.

## Preflight and readback

Run dry-run to validate only the static job/defaults.

## Public arguments and options

- `--job` (optional) — Path to a structured multicam job JSON file
- `--job-json` (optional) — Inline structured multicam job JSON
- `--angle` (optional, repeatable) — Repeatable source spec; repeat a label for separate sequential clips on one angle: A=camA.mov
- `--timeline-name` (optional) — Target timeline name for the multicam job
- `--multicam-name` (optional)
- `--sync-mode/--sync` (optional)
- `--cleanup-stale` (optional, default: `false`) — Remove DB-only stale target rows for this multicam/timeline name before creating
- `--replace-existing` (optional, default: `false`) — Alias for --cleanup-stale; live visible targets still fail

## Boundaries and gotchas

- `--job` and `--job-json` are mutually exclusive through the structured loader.
- Convenience mode requires `--timeline-name`.
- Angle labels do not need to be unique: repeat one label to place distinct clips sequentially on that logical angle.
- Default video/audio angles must belong to that order.
- Optional durations must be positive integers.
- Dry-run does not verify that convenience clip names or structured paths exist.
- `--replace-existing` is only an alias for `--cleanup-stale`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
