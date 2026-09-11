# `project preset load`

Syntax: `cutagent project preset load NAME`

## Search terms

- load project preset
- apply project settings preset
- DaVinci Resolve project preset
- dry-run preset validation
- project setting mutation
- available preset names

## What it does

Load project preset by name.

## Do not use when

Do not load a preset without first saving/exporting the project's current settings and understanding every setting the preset can change.
Do not rely on a name when preset listing contains duplicates; the last exact matching entry wins.

## Preflight and readback

Before execution, run `project preset list`, capture complete current project settings, confirm exact/case-sensitive preset name, and save/export the project.
Verify timelines, frame rate, color management, media, and representative render behavior.

## Public arguments and options

- `NAME` (required) — Preset name

## Boundaries and gotchas

- There is no `--force` or confirmation.
- A current project is required.
- If it returns an empty/list without the exact name, the command fails even in dry-run.
- Matching is exact/case-sensitive.
- Duplicate exact names overwrite the prior match, so the last matching object is used.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project preset load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
