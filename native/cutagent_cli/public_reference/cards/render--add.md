# `render add`

Syntax: `cutagent render add [--in VALUE] [--out VALUE]`

## Search terms

- add render job
- render queue enqueue
- render in out timecode
- full timeline render job
- Deliver page render job
- render output precondition
- MarkIn MarkOut
- preview render queue

## What it does

Add a render job to the queue.

## Do not use when

Do not add a job before configuring and verifying output target and filename through render settings.
Do not confuse queueing with starting a render.
Do not use `--in`/`--out` expecting absolute timeline frames.

## Preflight and readback

Run connected dry-run. Require correct `settings`, target/name, queue count, and output precondition. Verify MarkIn/MarkOut frame conversion and order.

## Public arguments and options

- `--in` (optional) — In point (timecode)
- `--out` (optional) — Out point (timecode)

## Boundaries and gotchas

- Exact help is `cutagent render add [--in TIMECODE] [--out TIMECODE]`.
- There is no `--force` or confirmation.
- Dry-run requires a timeline only when at least one mark is supplied; it still requires a project/render state.
- Range domain is fixed to `record` for this command.
- When both are supplied, in frame must be less than or equal to out frame.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent render add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
