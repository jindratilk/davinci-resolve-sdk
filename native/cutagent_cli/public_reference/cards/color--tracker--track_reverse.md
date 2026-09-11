# `color tracker track-reverse`

Syntax: `cutagent color tracker track-reverse TRACKER_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- track reverse
- analyze motion before current frame
- run Fusion Tracker backward
- follow subject toward clip start
- generate reverse tracking data
- track window through earlier frames
- start IntelliTrack reverse analysis
- calculate tracker path backward
- motion track from reference frame to start
- backtrack tracker
- reverse solve tracker
- analyze Tracker tool in reverse

## What it does

Trigger tracker reverse analysis.

## Do not use when

Use both directions deliberately when the reference is inside the clip and the whole range is required. Use `tracker add`/`set-target` first if the Tracker or target point is missing.

## Preflight and readback

Before running, save the project and export the comp; stop all project/comp renders; verify the exact Tracker, active point, current Fusion time/reference frame and intended earlier range. Ensure interactive access to DaVinci Resolve and record a PID/process recovery plan. Treat the environment timeout as a post-trigger poll limit, not an end-to-end command deadline.
On hang, stop the exact client, explicitly cancel the comp render in DaVinci Resolve, dismiss its confirmation, and check for partial data before retrying. A force restart may be necessary if the modal/event loop does not respond; preserve the project checkpoint first.

## Public arguments and options

- `TRACKER_NAME` (required) — Tracker tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- It does not prove reverse analysis started, reached frame 0, created keys, or tracked the intended feature.
- Dry-run resolves nothing and performs no render/modal readiness checks.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color tracker track-reverse --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
