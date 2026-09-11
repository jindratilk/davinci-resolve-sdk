# `fairlight record arm`

Syntax: `cutagent fairlight record arm [--track VALUE] [--enable]`

## Search terms

- arm audio track for recording
- record enable A1
- press Fairlight R button
- disarm recording track
- enable record on microphone track
- prepare track to record
- turn off track record arm
- set Fairlight track ready to record
- monitor input and arm track
- patch mic and arm audio track
- choose track for audio recording
- record-arm dialogue track

## What it does

Set Fairlight audio track record arm in DaVinci Resolve.

## Do not use when

Use DaVinci Resolve's visible Fairlight track-header R control to arm a track and the Patch Input/Output controls to choose the hardware input. Confirm the input meter and monitoring path manually before recording. Use the visible R control again to disarm.
Do not substitute `fairlight mute`, `fairlight lock`, or track enable/disable. Mute controls timeline contribution, lock controls editing, and record arm selects a track for capture; these are independent states.
After a manual recording exists as a timeline take, use supported clip inspection, rename, move, gain, cleanup, and processing commands.

## Preflight and readback

Supply `--track N` if you need the full structured blocker rather than the missing-option validation.
For the real manual workflow, first verify the active project/timeline, 1-based audio track identity, track format, hardware input device, sample rate, patch, input monitoring, storage path, and safe monitoring level.

## Public arguments and options

- `--track/-t` (optional) — Audio track index to arm
- `--enable/--disable` (optional, default: `true`) — Requested record-arm state

## Boundaries and gotchas

- `--track` is required even though the operation is unsupported.
- The default is `--enable`; a bare command with `--track 1` requests arm, not read.
- `--disable` means request disarm.
- It does not disable the audio track, monitoring subsystem, or recording feature globally.
- It is not wired to the public command and must not be invoked by inference.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight record arm --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
