# `clip cache`

Syntax: `cutagent clip cache [NAME] [--type VALUE] [--enable]`

## Search terms

- get clip render cache state
- enable color output cache on clip
- disable Fusion output cache
- force cache one timeline item
- inspect clip cache mode
- turn off cached output for occurrence
- control DaVinci Resolve clip cache
- check whether color cache is enabled

## What it does

Check clip cache state.

## Do not use when

Use `clip cache-state` for an explicitly read-only interface, and `clip cache-set` when Fusion mode `auto` is required. Do not use this to prove a frame has finished rendering into cache; it reports the item's requested output-cache mode only.

## Preflight and readback

Confirm global render-cache settings and available storage if enabling. After a mutation, inspect the returned readback and later check DaVinci Resolve's cache indicator/playback or cache files; immediate mode verification does not imply rendered cache completion. Restore the original mode after temporary diagnostics.

## Public arguments and options

- `NAME` (optional) — Clip name (or current if omitted)
- `--type` (optional, default: `"color"`) — Cache type: color or fusion
- `--enable/--disable` (optional) — Enable or disable output cache

## Boundaries and gotchas

- The option is a boolean toggle: color and Fusion can be enabled or disabled, but this command cannot set Fusion back to `auto`.
- Use `clip cache-set --type fusion --mode auto` for that.
- The command does not start/wait for a completed render, return progress, inspect cache validity, or prove playback is using cached frames.
- Passing both `--enable` and `--disable` is explicitly rejected rather than choosing one.

## Examples

- `cutagent clip cache --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
