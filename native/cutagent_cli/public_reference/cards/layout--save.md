# `layout save`

Syntax: `cutagent layout save NAME`

## Search terms

- save DaVinci Resolve layout preset
- create workspace layout preset
- preserve current UI layout
- layout recovery preset
- save layout dry-run
- duplicate layout preset name
- embedded layout save unsupported

## What it does

Save the current layout as a preset.

## Do not use when

Do not use an untrusted, empty, or collision-prone name.

## Preflight and readback

Before execution, capture the current page, panels, viewers, screen arrangement, project/timeline, and existing Workspace > Layout Presets entries. Choose a globally unique temporary name.
Dry-run does not detect name collisions.
Test load against the same current state before relying on it as recovery.

## Public arguments and options

- `NAME` (required) — Layout preset name

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout save --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
