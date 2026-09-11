# `media mark set`

Syntax: `cutagent media mark set CLIP --in VALUE --out VALUE [--type VALUE]`

## Search terms

- set Media Pool in out
- choose source clip range
- mark usable part of source
- set audio source trim points
- define source selection
- set clip source in and out frames
- mark portion before append

## What it does

Set mark in and out points for a media pool item.

## Do not use when

Use `timeline mark set` for the active timeline's playback/render in/out range. Use explicit source-start/source-end options on media append/edit commands when one insertion needs bounds without changing shared Media Pool state. Do not use this to change a timeline item's current source trim after it is already edited; choose the relevant timeline trim/duration command.

## Preflight and readback

Preserve and restore prior category ranges around temporary edit workflows.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `--in` (required) — Mark-in frame
- `--out` (required) — Mark-out frame
- `--type` (optional, default: `"all"`) — all|video|audio

## Boundaries and gotchas

- Default `--type all` applies the range to the streams present.
- Setting marks changes shared Media Pool state that can influence user source-selection workflows; it does not retrospectively alter existing timeline clips.
- Dry-run does not resolve the clip, validate bounds, or inspect existing marks.

## Examples

- `cutagent media mark set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
