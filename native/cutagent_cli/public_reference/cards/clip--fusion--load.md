# `clip fusion load`

Syntax: `cutagent clip fusion load CLIP --comp VALUE`

## Search terms

- switch active Fusion composition
- load Fusion comp by name
- open composition version on clip
- activate named Fusion graph
- change current comp for timeline item
- choose Fusion composition before import

## What it does

Switch to a Fusion composition by name.

## Do not use when

Do not use this command as existence validation: its current success criteria allowed a nonexistent name.

## Preflight and readback

List comps, resolve the intended current index/name independently, and export important graphs before switching.

## Public arguments and options

- `CLIP` (required) — Clip name
- `--comp` (required) — Fusion composition name

## Boundaries and gotchas

- There is no `--track`/`--at` selector.
- Do not expect dry-run protection.
- Loading does not rename, add, delete, or validate a comp.

## Examples

- `cutagent clip fusion load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
