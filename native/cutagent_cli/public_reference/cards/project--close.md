# `project close`

Syntax: `cutagent project close`

## Search terms

- close current DaVinci Resolve project
- close without saving
- close stuck project
- Project Manager context
- noninteractive project close

## What it does

Close the current project without saving.

## Do not use when

Do not use this when unsaved work must be preserved. Explicitly run and verify `project save` first.
Do not use it to exit DaVinci Resolve or close the Project Manager window. It targets only the current project.
The close condition is that the original project is no longer current.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Global dry-run returns before connecting or requiring a project.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project close --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
