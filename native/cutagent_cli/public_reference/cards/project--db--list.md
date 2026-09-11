# `project db list`

Syntax: `cutagent project db list`

## Search terms

- list DaVinci Resolve databases
- project libraries
- project manager databases
- current library candidates

## What it does

List project storage locations.

## Do not use when

Do not expect filtering by type/name/IP; the command exposes no options.
Do not assume an empty successful list proves there are no databases.

## Preflight and readback

After execution, use stable `type` and exact `name`, not the one-based presentation index, for subsequent operations.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no command-specific options; `--type` is invalid.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project db list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
