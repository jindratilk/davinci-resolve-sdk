# `fairlight track-format set`

Syntax: `cutagent fairlight track-format set INDEX [--track-type VALUE]`

## Search terms

- change Fairlight track format
- convert audio track to mono
- make A1 stereo
- set 5.1 Fairlight track
- change audio channel layout
- convert track to adaptive
- set surround track format
- make dialogue lane mono
- change existing audio subtype
- set 7.1 film track
- convert stereo track to mono
- change LCR track layout

## What it does

Set an existing Fairlight audio track format in DaVinci Resolve.

## Do not use when

This command mutates an existing track in place.
Use `fairlight track duplicate` when the goal is a new track based on the source track's format/name/state and optionally clips. Track-format does not copy anything.
Use clip audio-channel mapping commands when the source media's channel interpretation should change. A track layout and a clip/media audio mapping are separate contracts.
Do not use `mono` as a downmix operation. The command changes the track subtype but does not render, fold down, combine stereo clip channels, change clip attributes or prove the resulting audible mix.
Likewise `lrc` and `lcr` are separate accepted layouts.

## Preflight and readback

Before mutation, run `project info`, `timeline info` and `fairlight tracks`. Use a saved test-project checkpoint, especially when the track contains media.
Dry-run validates the format string but not whether the target index exists.
Run `fairlight tracks` after reopen and confirm the new format on the same track identity.

## Public arguments and options

- `INDEX` (required) — Audio track index
- `--track-type` (optional, default: `"stereo"`) — Requested audio format

## Boundaries and gotchas

- It does not create a new track or migrate clips through DaVinci Resolve's normal GUI conversion workflow.
- The bare legacy alias `adaptive` becomes `adaptive1`; it does not infer channel count from clips.
- Behavior with real stereo/surround clips, plugins and buses was not promoted from subtype readback alone; render verification is required.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight track-format set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
