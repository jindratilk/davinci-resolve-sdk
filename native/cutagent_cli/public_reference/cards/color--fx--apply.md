# `color fx apply`

Syntax: `cutagent color fx apply NAME [--clip VALUE] [--item-id VALUE] [--track VALUE] [--record-frame VALUE] [--template VALUE] [--params VALUE] [--verify] [--proof-dir VALUE]`

## Search terms

- apply reviewed Fusion color effect
- stable color effect ID
- typed effect parameter ranges
- apply custom reviewed setting
- rendered before after proof

## What it does

Apply a Fusion grading effect.

## Do not use when

Use generic Fusion commands for arbitrary topology. Do not pass unreviewed templates, arbitrary raw replacements, or `--no-verify`.

## Public arguments and options

- `NAME` (required) — Reviewed effect ID or alias
- `--clip` (optional) — Target timeline clip
- `--item-id` (optional)
- `--track` (optional) — Exact video track index; requires --record-frame
- `--record-frame/--at` (optional) — Record-domain position inside the target
- `--template` (optional) — Reviewed custom .setting path with sibling manifest
- `--params` (optional) — JSON object of reviewed parameter IDs and typed values
- `--verify/--no-verify` (optional, default: `true`) — Require structural and rendered verification
- `--proof-dir` (optional) — Directory for retained rendered evidence

## Boundaries and gotchas

- Global `--dry-run` validates and returns a plan without connecting to DaVinci Resolve.
- Duplicate or stale targets fail closed instead of choosing the first name match.
- Verification is mandatory and includes rendered pixels; pre-existing same-type tools cannot satisfy exact identity verification.

## Stable public error codes

- `AMBIGUOUS_TIMELINE_ITEM`
- `EFFECT_NOT_SUPPORTED`
- `EFFECT_PARAMETER_INVALID`
- `EFFECT_VERIFICATION_FAILED`
- `STALE_TIMELINE_ITEM`

## Examples

- `cutagent color fx apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
