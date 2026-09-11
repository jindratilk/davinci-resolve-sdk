# `project preset delete`

Syntax: `cutagent project preset delete NAME [--force]`

## Search terms

- project preset delete
- Delete a project settings preset.
- project preset delete help
- project preset delete command

## What it does

Delete a project settings preset.

## Do not use when

Do not use this command for render presets, keyboard presets, projects, timelines, or media.
Do not delete a preset unless its exact name and removal are intended.
Do not assume a reported failure means nothing changed.

## Preflight and readback

After execution, require `deleted:true` and confirm the exact name is absent while all unrelated presets retain their original order.

## Public arguments and options

- `NAME` (required) — Exact preset name
- `--force/-f` (optional, default: `false`) — Confirm deletion

## Boundaries and gotchas

- Exact syntax is `cutagent project preset delete NAME --force` in JSON/machine mode.
- Preset matching is exact and case-sensitive; missing, duplicate, malformed, or ambiguous records fail closed before deletion.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent project preset delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
