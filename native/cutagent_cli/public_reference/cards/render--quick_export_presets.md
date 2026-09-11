# `render quick-export-presets`

Syntax: `cutagent render quick-export-presets`

## Search terms

- list Quick Export presets
- available quick export names
- DaVinci Resolve 20 presets
- quick-export selector source
- Quick Export preset index
- inspect one-click render choices
- current project quick export catalog

## What it does

List available quick export presets.

## Preflight and readback

Before execution, ensure the embedded bridge is running, DaVinci Resolve 20+ has an active project, and the intended project is current.
Record the exact returned name and 1-based position before calling `render quick-export`; exact names are safer than aliases or partial selectors.
After changing Quick Export configuration in DaVinci Resolve, rerun the command rather than relying on an old list. After an actual Quick Export, verify the output media independently because this listing says nothing about render success.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The list does not mark built-in versus custom presets.
- It does not identify which preset is currently selected elsewhere in the UI.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render quick-export-presets --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
