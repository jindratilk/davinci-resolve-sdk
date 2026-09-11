# `timeline frame-export`

Syntax: `cutagent timeline frame-export --at VALUE --output VALUE`

## Search terms

- export timeline frame
- still at playhead position
- visual timeline proof
- restore playhead after still
- export PNG from timeline
- timeline timecode screenshot
- rendered frame verification

## What it does

Export a still image from the timeline.

## Do not use when

Do not use this command for a Gallery still, current-playhead-only export without a target position, multi-frame sequence, contact sheet, preview video, or rendered deliverable. Use the narrower still, thumbnail, batch, preview, or render command.
The command does not preflight or preserve an existing destination.

## Preflight and readback

Before execution, inspect the active timeline, FPS/start/end frame, target record reference, original playhead, current DaVinci Resolve page/modal state, destination parent, and overwrite risk.
Use dry-run to inspect the absolute destination and intended playhead/export/restore actions.
Open the exported image and compare it with the intended timeline frame.

## Public arguments and options

- `--at` (required) — Timeline position to sample: timecode, seconds, or frames
- `--output/-o` (required) — Output image path

## Boundaries and gotchas

- Exact help is `cutagent timeline frame-export --at REF --output PATH`.
- `--at` and `--output`/`-o` are required.
- The command does not create the output parent.
- The command does not explicitly restrict or normalize the output extension.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_TIME_REFERENCE`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline frame-export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
