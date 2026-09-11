# `project rename`

Syntax: `cutagent project rename NAME`

## Search terms

- rename current DaVinci Resolve project
- Project Rename
- project rename readback
- project name validation
- current project mutation
- project naming collision

## What it does

Rename the current project.

## Do not use when

Do not use whitespace-only names or any ASCII control/delete character.

## Public arguments and options

- `NAME` (required) — New project name

## Boundaries and gotchas

- There is no `--force` or confirmation.
- Old name must be readable/nonempty.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
