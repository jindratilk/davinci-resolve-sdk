# `burnin preset import`

Syntax: `cutagent burnin preset import PATH`

## Search terms

- import data burn-in preset
- install window burn configuration
- add timecode overlay preset from file
- load shared slate overlay file
- register review watermark preset
- bring burn-in settings into DaVinci Resolve
- install data burn preset globally

## What it does

Import a burn-in preset.

## Do not use when

Use `burnin load` after import when the preset should become active. Use `burnin preset export` to create a portable file from an existing preset. Do not import an untrusted or unverified file into a production user profile merely because the extension/name looks plausible.

## Preflight and readback

After import, reopen the UI catalog, verify the exact derived name and every field/style, explicitly load it in a disposable project, and render a frame.

## Public arguments and options

- `PATH` (required) — Burn-in preset file path

## Boundaries and gotchas

- Cleanup must be performed through DaVinci Resolve's Data Burn-In preset UI or other authorized profile maintenance.
- The command does not require an open project, so accidental imports can alter the global catalog even when the intended project context is absent.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent burnin preset import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
