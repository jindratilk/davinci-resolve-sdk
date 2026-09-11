# `project db current`

Syntax: `cutagent project db current`

## Search terms

- project db current
- Check the current project storage location.
- project db current help
- project db current command

## What it does

Check the current project storage location.

## Do not use when

Do not silently ignore missing output in scripts.

## Preflight and readback

Before execution, ensure DaVinci Resolve and the CutAgent embedded bridge are connected.
After execution, distinguish direct from inferred details.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no command-specific options; `--type` is invalid here.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project db current --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
