# `media info`

Syntax: `cutagent media info NAME`

## Search terms

- inspect Media Pool clip properties
- get clip codec and sample rate
- show media source path
- check clip duration and FPS
- get detailed asset metadata
- inspect timeline Media Pool entry
- verify audio channels
- find clip online status

## What it does

Check detailed clip information.

## Do not use when

Use `media list`/`search` to disambiguate names before calling this. Use `timeline info` for active timeline settings and structural state rather than the timeline's Media Pool clip properties.

## Preflight and readback

Extract only the fields relevant to the next command and treat empty strings as unavailable rather than zero.

## Public arguments and options

- `NAME` (required) — Clip name

## Examples

- `cutagent media info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
