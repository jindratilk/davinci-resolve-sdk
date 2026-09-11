# `render custom-range`

Syntax: `cutagent render custom-range --in VALUE --out VALUE [--range-domain VALUE] [--start] [--wait]`

## Search terms

- render custom timeline range
- queue in out render
- record domain render marks
- absolute timecode render
- MarkIn MarkOut render settings
- enqueue and start render job
- render range no wait
- render range no start
- timeline start frame offset

## What it does

Queue render for a custom range.

## Do not use when

Do not use `--range-domain absolute` for offsets measured from timeline content start; absolute references do not add the timeline start frame.
Do not use `--no-start` without also specifying `--no-wait`.
Do not assume an error after enqueue removes the new job. Start and wait failures can leave the job queued or partially rendered.

## Preflight and readback

Before execution, record the active timeline, FPS, start frame/timecode, current Deliver settings, queue contents, destination, and filename. Convert both references in the intended domain and verify in is less than or equal to out.
After execution, query the queue by returned JobId. If waiting was requested, inspect terminal status and the output file.

## Public arguments and options

- `--in` (required) — In reference
- `--out` (required) — Out reference
- `--range-domain` (optional, default: `"record"`) — Range reference domain: record adds the timeline start frame; absolute uses the parsed frame/timecode directly
- `--start/--no-start` (optional, default: `true`) — Start render immediately
- `--wait/--no-wait` (optional, default: `true`) — Wait for completion

## Boundaries and gotchas

- Exact help is `cutagent render custom-range --in TEXT --out TEXT [OPTIONS]`.
- Both in and out options are required by the CLI.
- Defaults are `range-domain=record`, start enabled, and wait enabled.
- Valid enqueue-only usage is `--no-start --no-wait`.
- `absolute-record`, `timeline`, and `absolute-timeline` are accepted aliases for absolute even though help names only `record` and `absolute`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render custom-range --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
