# `timeline switch`

Syntax: `cutagent timeline switch [NAME] [--index VALUE]`

## Search terms

- switch active timeline
- open another sequence
- make timeline current
- change timeline by name
- go to a different edit
- activate sequence
- return to previous timeline

## What it does

Switch to a different timeline.

## Do not use when

Do not use this to open a different project (`project open`), rename a timeline (`timeline rename`), or navigate the visible Edit/Color/Fairlight page (`page switch`). Do not use a stale index after create/delete operations; resolve the current index with `timeline list` or use exact name. Do not assume switching restores a remembered GUI clip selection or page/panel context; those are separate states.

## Preflight and readback

Run `timeline list` and capture the current timeline plus exact target identity. Provide name or index, never both. Before returning to a previous edit, preserve its name rather than assuming its old index remains stable.

## Public arguments and options

- `NAME` (optional) — Timeline name
- `--index/-i` (optional) — Timeline index

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
