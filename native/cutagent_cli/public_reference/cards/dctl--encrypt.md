# `dctl encrypt`

Syntax: `cutagent dctl encrypt INPUT_PATH OUTPUT_PATH [--expiry VALUE] [--overwrite]`

## Search terms

- encrypt DCTL
- create .dctle
- protect DCTL source
- EncryptDCTL
- set DCTL expiry

## What it does

Create an encrypted DCTL artifact.

## Do not use when

Do not use this command with DaVinci Resolve Free or a DaVinci Resolve version before 21.1. Use `dctl install` for an existing DCTL artifact and `dctl apply` for applying an installed DCTL to a clip.
Do not overwrite the only copy of an encrypted artifact without preserving it separately.

## Preflight and readback

Add `--overwrite` only when replacing that exact existing file is intended.
The public SDK has no managed artifact carrier for this operation yet, so route it through CutAgent CLI rather than inventing a typed SDK executor.

## Public arguments and options

- `INPUT_PATH` (required) — Source .dctl file path
- `OUTPUT_PATH` (required) — Exact output .dctle file path
- `--expiry` (optional) — Optional ISO 8601 expiry date or datetime
- `--overwrite` (optional, default: `false`) — Replace an existing output artifact

## Boundaries and gotchas

- CutAgent validates and normalizes its syntax but cannot recover an expired artifact.
- This is a CLI-only artifact mutation until a reviewed public SDK managed-file carrier exists.

## DaVinci Resolve editions

Do not use this command with DaVinci Resolve Free or a DaVinci Resolve version before 21.1.

## Examples

- `cutagent dctl encrypt --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
