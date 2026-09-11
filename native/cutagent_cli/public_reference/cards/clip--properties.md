# `clip properties`

Syntax: `cutagent clip properties [NAME] [--get VALUE] [--set VALUE] [--value VALUE]`

## Search terms

- list timeline item properties
- get ZoomX from clip
- set raw DaVinci Resolve clip property
- inspect transform property dictionary

## What it does

Check clip properties.

## Preflight and readback

After a reported success, immediately `--get` the same key and inspect the visible/rendered result.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--get` (optional) — Get specific property
- `--set` (optional) — Set property key
- `--value` (optional) — Set property value

## Boundaries and gotchas

- Readability does not imply writability.
- DaVinci Resolve may expose keys that are read-only, item-type-specific, or require another page/state.
- That label does not mean a particular key is supported for writing.
- Exactly one mode is allowed: `--get` alone, `--set` together with `--value`, or neither for all.
- There is no `--at` selector.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent clip properties --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
