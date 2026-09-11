# `fairlight bus assign`

Syntax: `cutagent fairlight bus assign [BUS] [--track VALUE] [--track-name VALUE]`

## Search terms

- assign audio track to Main bus
- route track to Bus 1
- verify default output routing
- check track can use Main output
- connect Fairlight track to bus
- set track output bus
- route audio track to Main 1
- verify track and default bus exist
- Fairlight bus assignment
- check Bus 1 model
- validate track-to-output route

## What it does

Verify Fairlight bus assignment through the output.

## Do not use when

Do not use this command to satisfy a request to route a track to a bus.
Do not use it to prove that a track is currently feeding Main. Use an actual routing graph/track-output getter if one becomes available.
Use `fairlight bounce mix-to-track` to print the Main mix, not to establish per-track routing.

## Preflight and readback

Before running, make the intended timeline active, list its audio tracks and capture the exact index/name.
Do not perform a post-mutation comparison because there was no mutation. If routing truth matters, verify it independently in the DaVinci Resolve Fairlight UI or through a future supported route.

## Public arguments and options

- `BUS` (optional) — Destination bus name, e.g. 'Bus 1' or 'Main 1'
- `--track/-t` (optional) — Audio track index to route
- `--track-name` (optional) — Audio track name to route

## Boundaries and gotchas

- Therefore the default-bus check cannot fail for missing model evidence.
- Such buses cannot be selected by this command.
- At least one track selector is required.
- If both are supplied, `--track` silently takes precedence and `--track-name` is ignored.
- `--track-name` matching is exact and case-sensitive.
- Dry-run never connects or validates the track.
- Studio/Free does not change the no-op semantics.

## Examples

- `cutagent fairlight bus assign --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
