# `render preset-save`

Syntax: `cutagent render preset-save NAME`

## Search terms

- save render preset
- create custom render preset
- capture current Deliver settings
- reusable render configuration
- prepare preset for export

## What it does

Save current render settings as a preset.

## Do not use when

Export separately with `render export-preset` when a portable bundle is needed.

## Preflight and readback

Inspect current render settings and list existing presets. Choose a unique non-empty name and run `cutagent --json render preset-save "New preset name"`. The command rejects conflicting names before writing and checks the resulting catalog.

## Public arguments and options

- `NAME` (required) — Preset name

## Boundaries and gotchas

- Captures settings current at execution time; does not accept individual render-setting overrides.
- Does not queue or start rendering.
- Does not automatically delete a named preset after an uncertain write.

## Examples

- `cutagent render preset-save --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
