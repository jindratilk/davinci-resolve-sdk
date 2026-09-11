# `clip cache-state`

Syntax: `cutagent clip cache-state [CLIP] [--type VALUE]`

## Search terms

- is color output cache enabled
- inspect Fusion cache state
- verify cache toggle readback
- compare color and Fusion cache modes

## What it does

Check clip cache state.

## Do not use when

Do not interpret `mode: enable` as `cache complete`.

## Preflight and readback

Confirm the active timeline and exact occurrence, then query color and Fusion separately. Before changing modes, preserve these values so they can be restored. After `clip cache`/`cache-set`, rerun this readback and, separately, inspect DaVinci Resolve's cache indicator and playback/render behavior.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)
- `--type` (optional, default: `"color"`) — Cache type: color or fusion

## Boundaries and gotchas

- Color output cache supports only enable/disable through the setter, while Fusion also supports auto.

## Examples

- `cutagent clip cache-state --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
