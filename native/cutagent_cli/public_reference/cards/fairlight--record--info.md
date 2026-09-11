# `fairlight record info`

Syntax: `cutagent fairlight record info [--limit VALUE]`

## Search terms

- inspect Fairlight recording setup
- find audio record target folder
- inspect saved recording format
- check record start and end frames
- inspect DaVinci Resolve record metadata
- check recording completion percentage
- diagnose saved Fairlight recording job

## What it does

Check Fairlight record setup.

## Do not use when

Do not use this command to decide whether a specific track is currently armed, input-monitored, or patched.
Use normal timeline/clip/media inspection when the task is to find actual recorded takes, their current timeline placement, source file paths, durations, or waveform/audio content.
Use project/timeline settings commands for current documented capture/playout preferences. Neither should be conflated with per-track record state.
Do not use it for render queue/status.

## Preflight and readback

Before reading, ensure the intended local Disk project is open and saved.
Do not assume the first row belongs to the active timeline.

## Public arguments and options

- `--limit` (optional, default: `20`) — Maximum stored record setup/status rows to read

## Boundaries and gotchas

- A loaded project is required, but an active timeline is not.
- `--limit` defaults to 20 and must be at least 1.
- `--limit 0` fails in CLI validation before any project access.
- `found` reflects only whether the returned slice contains rows.
- That does not discard the record-info row.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight record info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
