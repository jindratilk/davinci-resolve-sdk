# `color graph inspect`

Syntax: `cutagent color graph inspect [--clip VALUE] [--comp VALUE]`

## Search terms

- inspect Fusion grading graph
- show MediaIn MediaOut connections
- list color windows qualifiers trackers
- find disconnected Fusion color tools
- inspect clip-attached ColorCorrector chain
- view Fusion mask chain topology

## What it does

Inspect clip-attached Fusion grading graph state.

## Preflight and readback

Confirm the target clip and comp index with `clip fusion list`, then inspect before repair/normalize/flatten to retain active and orphan classifications.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The command validates `--comp >= 1` and rejects an empty explicit clip before connecting.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color graph inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
