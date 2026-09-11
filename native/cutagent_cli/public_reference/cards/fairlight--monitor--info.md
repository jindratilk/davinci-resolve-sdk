# `fairlight monitor info`

Syntax: `cutagent fairlight monitor info [--limit VALUE]`

## Search terms

- inspect Fairlight monitor setup
- inspect TargetMonitor
- query MuteAudio
- inspect MasterAudioDisable
- check saved audio monitor configuration
- inspect panel beep recording preferences
- check whether monitor setup row exists
- inspect audio output setup metadata

## What it does

Read stored Fairlight monitor and audio setup rows from the DaVinci Resolve project.

## Do not use when

Do not use this command to answer “what is the current monitor level?”, “is Control Room muted right now?”, “which speakers are active?”, or “is DIM on?”.

## Preflight and readback

Before the read, confirm and save the intended local Disk project so relevant preferences have had a chance to persist. A timeline is not required. If a timeline is active, retain its name only as project-context evidence; monitor rows are not scoped to that timeline by the reader.
Record the row ID and Resolve version.
If the workflow needs current monitoring proof, inspect the visible Control Room during playback or query the physical monitor controller separately. Do not run a setter based only on this output.

## Public arguments and options

- `--limit` (optional, default: `20`) — Maximum stored monitor setup rows to read

## Boundaries and gotchas

- `found` is true only when total count is nonzero.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight monitor info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
