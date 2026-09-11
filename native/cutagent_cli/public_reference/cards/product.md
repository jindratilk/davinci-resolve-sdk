# `product`

Syntax: `cutagent product`

## Search terms

- DaVinci Resolve product name
- Studio or Free product identity
- which DaVinci Resolve edition is running
- detect DaVinci Resolve Studio
- detect DaVinci Resolve Free
- application product identity
- edition preflight

## What it does

Check the installed DaVinci Resolve edition.

## Do not use when

Do not use it to discover the current project/timeline; use `status`, `connect`, or `context`.

## Preflight and readback

It has no mutation to verify; if the user changes which DaVinci Resolve installation/edition is running, rerun `product` after reconnection.

## Public arguments and options

This command has no command-specific arguments or options.

## DaVinci Resolve editions

It returns the non-empty trimmed product string exactly as supplied by the running application, for example `DaVinci Resolve Studio`.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent product --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
