# `multicam flatten`

Syntax: `cutagent multicam flatten --timeline VALUE [--grade-policy VALUE] [--angle VALUE] [--scope VALUE] [--force]`

## Search terms

- flatten multicam
- preserve multicam grade
- retain angle grade
- replace multicam wrapper

## What it does

Flatten multicam clips on the timeline.

## Do not use when

Do not flatten before inspecting selector state and source matches. Do not use on ordinary non-multicam clips or when the user wants to keep editable multicam wrappers.

## Preflight and readback

Checkpoint the project, inspect target items, and dry-run.

## Public arguments and options

- `--timeline` (required)
- `--grade-policy` (optional, default: `"copy_multicam"`) — Flatten grade policy: copy_multicam or retain_angle
- `--angle` (optional) — Override the selected angle for every matching wrapper; otherwise decode each persistent selector
- `--scope` (optional, default: `"both"`) — Flatten video, audio, or both
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- `--timeline` is required.

## Examples

- `cutagent multicam flatten --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
