# `dctl validate-source`

Syntax: `cutagent dctl validate-source SOURCE`

## Search terms

- dctl validate-source
- Read DCTL diagnostics from DaVinci Resolve Studio 21.1+.
- dctl validate-source help
- dctl validate-source command

## What it does

Read DCTL diagnostics from DaVinci Resolve Studio 21.1+.

## Do not use when

Do not use to apply a grade, install a file, or claim a visible effect. For lightweight file checks use dctl validate instead.

## Preflight and readback

Pass the actual source text as the positional argument. A successful command response can contain valid false when the source has diagnostics.

## Public arguments and options

- `SOURCE` (required) — DCTL source text, up to 65536 UTF-8 bytes

## Boundaries and gotchas

- Source must be nonempty text, without null characters, and no larger than 65536 UTF-8 bytes.
- No open project is required.

## DaVinci Resolve editions

Checks supplied DCTL source text using DaVinci Resolve Studio 21.1 or newer.

## Examples

- `cutagent dctl validate-source --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
