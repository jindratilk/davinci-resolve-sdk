# `timeline voice-isolation set`

Syntax: `cutagent timeline voice-isolation set TRACK [--enable] [--amount VALUE]`

## Search terms

- set track voice isolation
- enable Fairlight Voice Isolation
- disable audio track isolation
- set Voice Isolation amount
- timeline audio track enhancement

## What it does

Set timeline voice isolation state.

## Do not use when

Do not use this for clip-level Voice Isolation; use the TimelineItem/clip-level Fairlight AI route.

## Public arguments and options

- `TRACK` (required) — Audio track index
- `--enable/--disable` (optional) — Enable or disable voice isolation
- `--amount` (optional) — Isolation amount 0-100

## Boundaries and gotchas

- Exact help is `cutagent timeline voice-isolation set TRACK [--enable|--disable] [--amount INT]`.
- `--amount` is an integer percentage-like value from 0 through 100, not a 0.0–1.0 fraction.
- At least one state option is not required.
- If `--enable`/`--disable` is omitted, `isEnabled` defaults from current `isEnabled`, or false when missing.
- If `--amount` is omitted, a current `amount` is preserved when present.
- Those fallbacks may operate on a broader/current scope while output still labels the requested track.
- Exact boolean `isEnabled` and integer `amount` must both be present and match.
- Global dry-run has a genuine early return and does not connect or write.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline voice-isolation set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
