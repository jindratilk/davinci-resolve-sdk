# `render presets`

Syntax: `cutagent render presets`

## Search terms

- list render presets
- available Deliver presets
- custom render preset names
- built-in render presets
- find preset selector
- inspect render preset catalog
- preset-load input names
- export-preset selector source

## What it does

List available render presets.

## Do not use when

Do not assume ordering, uniqueness, or canonical display names have been normalized by CutAgent CLI.

## Preflight and readback

Before execution, ensure the embedded bridge is running, a project is open, and the intended project is current.
Use the returned exact names as selectors for `render preset-load`, `render preset-delete`, or `render export-preset`; avoid partial selectors when similarly named presets exist.
After any preset save, import, or delete operation, rerun this command and compare the exact list. For a saved or loaded preset, separately inspect `render settings` because listing does not verify its content.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The listing does not identify built-in versus custom presets.
- It does not identify the currently loaded preset.
- It does not verify that a listed preset is loadable or exportable.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render presets --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
