# `color tracker track-forward`

Syntax: `cutagent color tracker track-forward TRACKER_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- analyze motion after current frame
- follow subject toward clip end
- track window through later frames
- calculate tracker path ahead
- continue tracking to end

## What it does

Runs the public `color tracker track-forward` CutAgent command.

## Do not use when

Use `color tracker add` and `set-target` before this command when a Tracker/target does not exist. Use `track-reverse` when frames before the reference/current tracker context must be analyzed. Do not use it when a project render or comp render is already running, or when an unattended timeout/modal would be unsafe.

## Preflight and readback

Set the desired point and ensure the intended point—not an automatically added second IntelliTrack point—is selected. Choose a timeout appropriate to clip length/format/hardware and ensure manual access to DaVinci Resolve is available if abort leaves a warning.
Afterward, do not rely on `completed:true`: export/inspect the Tracker path, count keyframes and verify coverage from the intended start through the intended end. Scrub/render multiple frames to verify the window/matte follows the feature. On failure, inspect and clean partial path/modifier data, check comp render-idle state and dismiss any modal before retrying.

## Public arguments and options

- `TRACKER_NAME` (required) — Tracker tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Name resolution may silently fall back to the only Tracker if the requested name is wrong.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color tracker track-forward --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
