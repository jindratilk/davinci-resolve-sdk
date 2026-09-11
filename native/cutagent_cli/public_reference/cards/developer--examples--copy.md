# `developer examples copy`

Syntax: `cutagent developer examples copy SECTION NAME DEST [--overwrite]`

## Search terms

- copy DaVinci Resolve SDK example
- extract DCTL sample
- copy scripting example locally
- get OpenFX sample source
- copy codec plugin example
- copy Fusion template SDK file
- retrieve workflow integration sample
- clone one Developer SDK example
- copy Fuse example
- save SDK sample to workspace

## What it does

Copy a DaVinci Resolve example.

## Do not use when

Use the corresponding install command (`dctl install`, workflow/Fuse/OpenFX/codec installer, etc.) after reviewing/building the copy.

## Preflight and readback

Back up an occupied target before allowing overwrite.

## Public arguments and options

- `SECTION` (required) — SDK section
- `NAME` (required) — Example file name or relative path
- `DEST` (required) — Destination path
- `--overwrite` (optional, default: `false`) — Replace an existing destination

## Boundaries and gotchas

- Only the file basename itself is checked for a leading dot during enumeration.
- It copies one file only.
- Dry-run still enumerates the real SDK tree and performs conflict checks.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent developer examples copy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
