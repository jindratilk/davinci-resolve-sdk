# `layout delete`

Syntax: `cutagent layout delete NAME [--force]`

## Search terms

- delete DaVinci Resolve layout preset
- remove workspace layout
- delete UI preset
- layout delete force
- layout deletion confirmation
- missing layout delete failure
- embedded layout delete unsupported
- cleanup temporary layout preset

## What it does

Delete a layout preset.

## Do not use when

Do not delete a preset without exporting and hashing a recovery artifact first.
Do not use `--force` as an existence check.
Do not assume repeated deletion is idempotent.
Do not rely on dry-run to prove the target exists or is the intended preset; DaVinci Resolve exposes no public scripting list method.

## Preflight and readback

Before execution, independently inspect Workspace > Layout Presets, normalize the exact target name, and prove it is a test/authorized preset rather than an unrelated user preset.
Preserve the export until import/recovery testing completes.

## Public arguments and options

- `NAME` (required) — Layout preset name
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- `--force` and `-f` skip confirmation.
- Dry-run occurs before the confirmation branch and does not require `--force`.
- Dry-run does not check whether the preset exists.

## Stable public error codes

- `API_CALL_FAILED`
- `CONFIRMATION_REQUIRED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
