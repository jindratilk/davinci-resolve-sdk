# `fairlight mixer read`

Syntax: `cutagent fairlight mixer read [--track VALUE] [--bus VALUE]`

## Search terms

- inspect Fairlight mixer strip
- get A1 mixer state
- check audio track level and balance
- inspect saved mixer lanes
- audit Bus 1 mixer context
- see track format enabled locked clips
- diagnose missing mixer readback
- check whether track pan lane exists
- inspect output channel count
- preflight track mix controls
- query static Fairlight control values

## What it does

Read a Fairlight audio-track and main-output mixer context from the project.

## Do not use when

Use `fairlight mixer fader --track N` when a full fader-specific result or its detailed mapping failure is required; `mixer read` can silently omit the fader when pan succeeds. Use `fairlight mixer pan --track N` for the corresponding complete pan result.
Use `fairlight tracks` or `fairlight info` for broader track inventory, display height, bus-label context, and unsupported-field diagnostics.
Use clip-level gain/pan commands for one occurrence, automation readers for time-varying control, and `fairlight mixer meter`/external audio analysis for signal amplitude.
Do not use the Main branch for `Bus 2`, Auxes, named FlexBuses, routing, or pan.

## Preflight and readback

Before a track read, save the project, run `fairlight tracks`, and confirm the intended index, name, subtype, channel count, materialized clips, enabled/locked state, and active timeline.
If one key is missing, run its dedicated reader to recover the suppressed diagnostic. Compare any value to the visible Fairlight control and a controlled audio signal before using it in an edit decision.
Before a Main read, record the exact requested alias, visible Bus 1/Main fader, project/timeline identity and output-channel count.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--bus` (optional) — Bus/main output name

## Boundaries and gotchas

- Exactly one selector is required.
- Do not infer that one successful lane validates the other.
- This command does not close/reopen the project and does not intentionally change page, focus, selection, playhead, clips, tracks, or mixer state.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight mixer read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
