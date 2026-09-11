# `project folders list`

Syntax: `cutagent project folders list`

## Search terms

- current Project Manager folder
- project library navigation
- current folder projects
- nonrecursive project folder list
- DaVinci Resolve Project Manager

## What it does

List folders in current project location.

## Do not use when

Do not expect recursive traversal. It lists only the current location and exposes no recursive option.
Do not use it to list databases or Media Pool bins.

## Preflight and readback

Treat returned child names as relative to that current location.
For recursive inventory, explicitly navigate and list each child while preserving a path stack; this command does not do it automatically.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--recursive` is invalid.
- Results are immediate children only.
- Global dry-run changes metadata but not execution.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project folders list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
