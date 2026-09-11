# `multicam recover-timing`

Syntax: `cutagent multicam recover-timing [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--source-specs VALUE] [--source-specs-json VALUE] [--apply-timemap] [--apply-source-start-tc] [--apply-media-extents] [--verify-reopen]`

## Search terms

- recover multicam timing
- recover source start timecode
- rewrite multicam media extents
- multicam source specs JSON
- verify multicam after reopen
- multicam timing dry-run

## What it does

Recover multicam timing.

## Do not use when

Do not use this as a generic sync tool or first-line repair.
Prefer exact media/sequence IDs obtained from inspection and require all supplied selectors to identify one record.
Do not use inferred source timing without reviewing its resolved clip/path/folder, FPS, duration, start timecode/frame, and offsets.

## Preflight and readback

Run dry-run with the minimum apply flags.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--source-specs` (optional) — Path to source spec JSON
- `--source-specs-json` (optional) — Inline source spec JSON
- `--apply-timemap` (optional, default: `false`)
- `--apply-source-start-tc` (optional, default: `false`) — Rewrite Start/Duration/MediaStartTime from source start timing
- `--apply-media-extents` (optional, default: `false`)
- `--verify-reopen` (optional, default: `false`) — After project reopen, confirm the multicam still exists in the Media Pool

## Boundaries and gotchas

- Exactly one of `--source-specs` and `--source-specs-json` is required.
- FPS must be positive.
- Duration frames must be a positive integer.
- Source start frame and source start offset must be nonnegative integers.
- Timecode accepts colon or semicolon frame notation and must agree with an explicitly supplied start frame.
- `--apply-source-start-tc` implies timemap rewrite and can replace item Start, Duration, and MediaStartTime.
- `--apply-media-extents` computes the sequence range from minimum source start+offset through maximum source end.
- Duplicate name matches are rejected as ambiguous with advice to use IDs.
- There is no command-specific `--force` flag.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam recover-timing --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
