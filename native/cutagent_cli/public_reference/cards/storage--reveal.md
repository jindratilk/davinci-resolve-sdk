# `storage reveal`

Syntax: `cutagent storage reveal PATH`

## Search terms

- reveal path in Media Storage
- navigate DaVinci Resolve storage panel
- show file in media browser
- MediaStorage UI selection
- locate media path
- open storage folder

## What it does

Reveal a path in DaVinci Resolve media storage.

## Do not use when

Do not expect the command to switch to a particular DaVinci Resolve page or verify what became visible.

## Preflight and readback

Before execution, verify the path independently, ensure changing Media Storage UI focus is acceptable, and make sure DaVinci Resolve is connected.
After execution, require `revealed: true` and visually inspect the Media Storage panel.

## Public arguments and options

- `PATH` (required) — Path to reveal in Media Storage

## Boundaries and gotchas

- Reveal changes application UI/navigation state even though it does not import media.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent storage reveal --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
