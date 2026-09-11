# `project folders root`

Syntax: `cutagent project folders root`

## Search terms

- GotoRootFolder
- Project Manager root navigation
- unwind project folders
- reset project folder context
- project library navigation
- folder hierarchy root

## What it does

Open to the root project folder.

## Do not use when

Do not rely on the returned `folder:"root"` as readback verification. Neither route queries the current folder afterward.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--force` is invalid.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project folders root --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
