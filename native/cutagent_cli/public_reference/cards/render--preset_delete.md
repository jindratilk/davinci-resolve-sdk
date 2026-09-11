# `render preset-delete`

Syntax: `cutagent render preset-delete NAME`

## Search terms

- delete render preset
- remove Deliver preset
- delete custom render preset
- preset deletion exact name
- remove saved render settings

## What it does

Delete a render preset.

## Do not use when

Do not delete a preset before exporting/backing it up if its configuration may be needed again.
Do not pass a numeric index, partial alias, or differently cased guess; this command does not resolve selectors against `render presets`.

## Preflight and readback

Use dry-run to inspect only the literal name that would be sent. It does not enumerate presets or validate deletability.
Confirm dependent workflows no longer reference it.

## Public arguments and options

- `NAME` (required) — Preset name

## Boundaries and gotchas

- The required argument is syntactic; an explicitly empty string reaches command logic.
- It does not distinguish custom from built-in presets.
- It does not verify that the preset disappeared.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent render preset-delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
