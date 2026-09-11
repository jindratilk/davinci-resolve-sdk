# `timeline current-item`

Syntax: `cutagent timeline current-item`

## Search terms

- current timeline video item
- clip under playhead
- inspect playhead clip
- current video clip bounds
- active timeline item track
- DaVinci Resolve modal readback
- playhead item metadata

## What it does

Inspect the clip under the playhead.

## Do not use when

Do not use this command to locate an audio-only or subtitle item under the playhead.
Do not use it to enumerate every item overlapping the playhead, inspect media-pool properties, or prove clip selection in the DaVinci Resolve UI. Use track/item listing or a narrower media-pool command for those questions.

## Preflight and readback

Before execution, make the intended project and timeline current and place the playhead over the video item of interest. Clear or inspect blocking DaVinci Resolve dialogs because a modal can make visual readback unavailable.
After execution, confirm the returned timeline name and playhead first, then check item name, bounds, duration, track type/index, and UI status.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not fall back to scanning video or audio tracks.
- Audio-only and subtitle items cannot be returned by this command.
- The response does not include media-pool identity, file path, source in/out, clip color, links, enabled state, or Fusion/color metadata.
- It does not enumerate neighboring or overlapping items.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent timeline current-item --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
