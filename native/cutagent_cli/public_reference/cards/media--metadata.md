# `media metadata`

Syntax: `cutagent media metadata [ARGS...]`

## Search terms

- set clip comments
- add keywords to source clip
- inspect clip metadata fields
- get one metadata value
- annotate footage in Media Pool
- set scene shot take metadata
- change project clip metadata

## What it does

Check clip metadata.

## Do not use when

Use `media third-party-metadata` for the separate third-party metadata namespace.

## Preflight and readback

Dry-run the exact quoted key/value. Store the old value for restoration because the setter response does not include it.

## Public arguments and options

- `ARGS` (optional, repeatable) — CLIP [KEY [VALUE]] or export FILE [CLIP...]

## Boundaries and gotchas

- Keys and values containing spaces must each be shell-quoted as one argument.
- A first positional token exactly equal to `export` enters the export branch, so an item literally named `export` cannot be addressed through the normal positional form.

## Examples

- `cutagent media metadata --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
