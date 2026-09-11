# `project preset save`

Syntax: `cutagent project preset save NAME`

## Search terms

- save project preset
- capture project settings preset
- DaVinci Resolve preset creation
- project preset name

## What it does

Save current project settings as a preset.

## Do not use when

Do not save a preset until the current project settings have been reviewed and intentionally configured.
Do not assume dry-run proves a project is open, a method exists, or the name is available.
Do not assume a success message proves the preset is listed/loadable; there is no post-save readback.

## Preflight and readback

Before execution, open the intended project, capture full settings, choose a unique descriptive preset name, and review any existing preset collision/overwrite behavior in DaVinci Resolve.

## Public arguments and options

- `NAME` (required) — Preset name

## Boundaries and gotchas

- There is no `--force` or confirmation.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project preset save --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
