# `media metadata export`

Syntax: `cutagent media metadata export FILE [CLIPS...]`

## Search terms

- export Media Pool metadata CSV
- export metadata for selected clips
- save footage comments and keywords
- create DaVinci Resolve metadata report
- export source clip technical metadata
- dump Media Pool metadata to file
- compare metadata across clips

## What it does

Export media pool metadata to a file.

## Do not use when

Use `media metadata CLIP [KEY]` for JSON readback consumed directly by an agent.

## Preflight and readback

Choose named clips explicitly and exact-search them before export, especially when duplicate display names exist. Ensure the destination parent is writable and treat an existing path as potentially replaceable. After the command, verify file existence, size, encoding, header, row count, and key values; do not rely only on `exported: true`.

## Public arguments and options

- `FILE` (required) — Output metadata file
- `CLIPS` (optional, repeatable) — Optional Media Pool clip names

## Examples

- `cutagent media metadata export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
