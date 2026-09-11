# `fairlight elastic enable`

Syntax: `cutagent fairlight elastic enable [--clip VALUE] [--enable] [--algorithm VALUE]`

## Search terms

- enable Elastic Wave on audio clip
- turn on pitch-preserving audio stretch
- choose Voice Elastic algorithm
- set General Purpose Elastic Wave
- enable Varispeed audio retimer
- disable Elastic Wave
- change Fairlight stretch algorithm
- prepare clip for Elastic timing points
- inspect or toggle clip retimer state

## What it does

Runs the public `fairlight elastic enable` CutAgent command.

## Do not use when

Do not use this command to stretch the clip or add timing points; use `fairlight elastic keyframe --ratio` for whole-clip duration change or `--time-point` for an explicit output-to-source map. Do not use it as proof that pitch preservation is enabled; the pitch-preservation storage flag remains unmapped, so verify audio by render when that matters.

## Preflight and readback

Checkpoint a disposable/test project and use `--dry-run` to validate algorithm spelling.

## Public arguments and options

- `--clip` (optional) — Timeline clip name or item id
- `--enable/--disable` (optional, default: `true`) — Requested Elastic Wave state
- `--algorithm` (optional, default: `"voice"`)

## Boundaries and gotchas

- `--disable` is not generally idempotent cleanup.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight elastic enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
