# `auto-edit multicam`

Syntax: `cutagent auto-edit multicam [--job VALUE] [--job-json VALUE]`

## Search terms

- execute structured multicam job
- apply explicit camera switch segments
- run custom multicam auto edit
- build multicam clip and switched timeline
- execute speaker transcript multicam job JSON
- execute audio activity multicam job JSON
- control multicam source offsets and angle order
- materialize multicam switch plan in DaVinci Resolve

## What it does

Create a multicam edit.

## Do not use when

Use `auto-edit podcast-edit` for a concise transcript-to-camera preset, or `auto-edit podcast-multicam --plan-only` when the agent needs a preview before mutation.

## Preflight and readback

Validate the JSON manually against the current source contract: unique angle labels, resolvable clip names/folders/paths, supported sync mode/angle count, unique output names, positive ordered segment ranges, and either segments or one supported rule program. Check the active Disk project, timeline fps/start timecode, source durations, synchronization evidence, and establish a disposable project/checkpoint.

## Public arguments and options

- `--job` (optional) — Path to a structured multicam job JSON file
- `--job-json` (optional) — Inline structured multicam job JSON

## Boundaries and gotchas

- There is no `--plan-only` option.
- Global `--dry-run` only says that a structured job would execute; it does not load or validate the supplied file, build segments, resolve sources, or reveal effective settings.
- Exactly one of `--job` and `--job-json` is required.
- The structured job loader's validation message/examples currently mention `multicam settings` rather than `auto-edit multicam`; treat that as stale guidance, not another required command path.
- Media Pool names alone may be ambiguous.
- Structured source entries can carry folder/source information, but the exact resolution result must be inspected before trusting which file was bound.
- It does not prove source sync, transcript correctness, source duration coverage, or actual visual camera choice for this job.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent auto-edit multicam --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
