# `multicam replace video`

Syntax: `cutagent multicam replace video [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--angle VALUE] [--source-in VALUE] [--start VALUE] [--duration VALUE] [--allow-short-source] [--force]`

## Search terms

- replace multicam angle video
- multicam source-in override
- multicam angle start frame
- allow short video source
- multicam video dry-run

## What it does

Update video items inside multicam angles.

## Do not use when

Do not use negative `source-in` or `start` values.
Do not use `--allow-short-source` as automatic clipping.
Do not accept MediaRef-only verification as proof of timing or visual correctness. Check start, source-in, duration, timemap, frame rate, selector behavior, playback, and render.

## Preflight and readback

Use nonnegative frame values and run dry-run.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--angle` (optional, repeatable) — DaVinci Resolve one-based angle video replacement: 3=/path/camera.braw
- `--source-in` (optional, repeatable) — Per-angle source in frame override: 3=120
- `--start` (optional, repeatable)
- `--duration` (optional, repeatable)
- `--allow-short-source` (optional, default: `false`)
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Angle text accepts a positive integer or case-insensitive `Angle N`.
- `--source-in`, `--start`, and `--duration` use repeatable `ANGLE=integer` syntax.
- Duplicate entries within each override option are rejected.
- Every override angle must also appear in `--angle`.
- CLI maps all override keys from one-based numbers to zero-based indices.
- If source duration cannot be derived, the bounds check is skipped even without the flag.
- `--allow-short-source` skips rejection; it does not clamp/trim the requested duration.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam replace video --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
