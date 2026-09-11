# `clip fusion by-name`

Syntax: `cutagent clip fusion by-name CLIP NAME`

## Search terms

- find Fusion comp by name
- resolve Composition1 alias
- map Fusion comp name to index
- look up comp number
- validate Fusion composition selector
- find Comp1 on clip
- get stable Fusion comp alias

## What it does

Find a Fusion composition.

## Do not use when

Use `clip fusion list` to enumerate the raw comp attributes actually returned by indexed composition objects, `clip fusion load` to request an active-comp switch, and `clip fusion tools` to inspect graph contents.

## Preflight and readback

List comps first and retain raw index/name rows. If identity matters, export that index or inspect its tools and compare against the intended graph.

## Public arguments and options

- `CLIP` (required) — Clip name
- `NAME` (required) — Fusion composition name

## Boundaries and gotchas

- Aliases are case-insensitive but otherwise exact after outer whitespace trim.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip fusion by-name --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
