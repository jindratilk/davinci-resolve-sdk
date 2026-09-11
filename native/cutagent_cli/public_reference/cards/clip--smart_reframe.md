# `clip smart-reframe`

Syntax: `cutagent clip smart-reframe [NAME] [--item-id VALUE] [--track VALUE] [--record-frame VALUE] [--operation-id VALUE] [--progress-file VALUE] [--cancel-request-file VALUE] [--proof-dir VALUE] [--poll-ms VALUE]`

## Search terms

- smart reframe clip
- auto follow subject in vertical crop
- reframe landscape to portrait
- track subject for new aspect ratio
- automatic pan for social crop
- long-running reframing operation

## What it does

Run Smart Reframe with phase progress and terminal rendered evidence.

## Do not use when

Do not use this as a complete landscape-to-portrait workflow when the destination timeline aspect ratio has not already been set. Use static `clip transform` for a fixed crop and deliberate keyframes for authored camera moves.

## Preflight and readback

Inspect the timeline aspect ratio and exact target before mutation. Prefer `--item-id`, or use `--track` with `--record-frame`, when names repeat.

## Public arguments and options

- `NAME` (optional) — Clip name (or current clip)
- `--item-id` (optional)
- `--track` (optional) — Exact video track index; requires --record-frame
- `--record-frame/--at` (optional) — Record-domain position inside the exact target
- `--operation-id` (optional) — Caller-supplied stable operation ID
- `--progress-file` (optional) — Atomic JSON progress journal path
- `--cancel-request-file` (optional) — Existence-based cancellation request path
- `--proof-dir` (optional) — Directory for retained rendered verification evidence
- `--poll-ms` (optional, default: `250`) — Cancellation/progress polling interval

## Boundaries and gotchas

- Global `--dry-run` returns a plan without connecting to or mutating DaVinci Resolve.
- Progress is phase-only.
- The command does not change timeline resolution or aspect ratio.

## Stable public error codes

- `AMBIGUOUS_TIMELINE_ITEM`
- `SMART_REFRAME_VERIFICATION_FAILED`
- `STALE_TIMELINE_ITEM`

## Examples

- `cutagent clip smart-reframe --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
