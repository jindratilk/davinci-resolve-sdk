# `edit insert`

Syntax: `cutagent edit insert CLIP_NAME --at VALUE [--in VALUE] [--out VALUE] [--track VALUE] [--audio-only] [--media-id VALUE] [--audio-track VALUE] [--include-linked-audio] [--project-id VALUE] [--timeline-id VALUE] [--revision VALUE]`

## Search terms

- place Media Pool clip at an exact record frame
- add a half-open source range to an empty timeline range
- put B-roll on an explicit video track
- preflight a non-ripple clip placement

## What it does

Place a clip into an empty range without ripple and verify exact readback.

## Do not use when

Use `edit overwrite` when an occupied record range should be replaced. Use `--video-only` when the selected source's audio state is intentionally irrelevant; otherwise unknown source-audio metadata fails closed.
Do not guess a duplicate Media Pool name, a zero-based track, or a stale project/timeline/revision. The command rejects all three.

## Preflight and readback

The command never reports a pending/manual success.

## Public arguments and options

- `CLIP_NAME` (required) — Media pool clip name
- `--at/--record-frame` (required) — Timeline record-domain position
- `--in/--source-in` (optional) — Half-open source-domain range start
- `--out/--source-out` (optional) — Half-open source-domain range end (exclusive)
- `--track` (optional, default: `1`) — One-based target video track, or audio track with --audio-only
- `--audio-only` (optional, default: `false`) — Insert the source as audio only on --track
- `--media-id` (optional) — Authoritative Media Pool item identity
- `--audio-track` (optional) — One-based linked-audio target track
- `--include-linked-audio/--video-only` (optional, default: `true`) — Insert and verify source audio when present
- `--project-id` (optional) — Expected active project identity
- `--timeline-id` (optional) — Expected active timeline identity
- `--revision` (optional) — Expected timeline revision from a prior dry run

## Boundaries and gotchas

- Every existing timeline item must expose a stable item ID and linked-item state.
- Every track must expose enabled/locked state.
- `--track` and `--audio-track` are one-based.
- Missing, locked or disabled tracks fail before mutation; the command does not create tracks.

## Stable public error codes

- `AMBIGUOUS_MEDIA_POOL_ITEM`
- `EDIT_MUTATION_FAILED_BEFORE_CHANGE`
- `EDIT_MUTATION_PARTIALLY_APPLIED`
- `INVALID_TIME_REFERENCE`
- `TIMELINE_CONFLICT`

## Examples

- `cutagent edit insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
