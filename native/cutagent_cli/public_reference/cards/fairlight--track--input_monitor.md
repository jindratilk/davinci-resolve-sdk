# `fairlight track input-monitor`

Syntax: `cutagent fairlight track input-monitor INDEX [--enable]`

## Search terms

- enable Fairlight input monitoring
- monitor microphone on audio track
- turn input echo on
- disable input monitor
- stop monitoring recording input
- route hardware input to track
- monitor patched input
- Fairlight input button
- listen to armed track
- input monitor A2
- toggle track monitoring
- monitor booth microphone

## What it does

Check Fairlight input monitoring availability.

## Do not use when

That command does not reveal per-track monitor state.
Do not use input-monitor as record-arm. Monitoring lets an input be heard; record arm determines which track will record.
Do not use mute/unmute, enable/disable, solo, fader or pan as substitutes.
Use ADR/voiceover workflow commands only for their documented preparation or capture boundaries.

## Preflight and readback

Before handing off to the GUI, identify the intended track with `fairlight tracks`, inspect `fairlight record info` and `fairlight io info`, and confirm the input device/channel in DaVinci Resolve Patch Input/Output.
Do not retry with `--dry-run` or another track index as if the error were target-specific.
After the user manually patches and enables/disables monitoring, verify in the Fairlight GUI and by listening/metering with safe gain.

## Public arguments and options

- `INDEX` (required) — Audio track index
- `--enable/--disable` (optional, default: `true`) — Requested input monitoring state

## Boundaries and gotchas

- `--enable` is the default.
- The command does not connect to DaVinci Resolve or validate index existence.
- Project-level capture settings do not identify a per-track monitor toggle.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight track input-monitor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
