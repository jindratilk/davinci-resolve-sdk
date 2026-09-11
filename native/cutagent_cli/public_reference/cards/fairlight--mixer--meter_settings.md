# `fairlight mixer meter-settings`

Syntax: `cutagent fairlight mixer meter-settings [--limit VALUE]`

## Search terms

- inspect AudioMeterDBUEnable
- get audio meter alignment level
- check dBu meter calibration
- see meter reference level
- check audio meter configuration
- audit Fairlight setup tables

## What it does

Read stored Fairlight audio-meter setup rows from the DaVinci Resolve project.

## Do not use when

It will not produce a measurement. For a real peak, RMS, true-peak, or LUFS result, render/export the intended audio and analyze that file; `meter-settings` contains preferences, not signal values.
Use `fairlight monitor info` for control-room/VTR/audio-monitor setup rows, and `fairlight record info` for recording setup semantics.
Use `fairlight mixer read` for static fader and pan context.
Do not use this command to change dBu mode, calibration, recording format, mute, or any returned field.

## Preflight and readback

A timeline is not required, but project identity is.
Treat `found:false` with available empty tables as a successful observation that no persisted rows exist.

## Public arguments and options

- `--limit` (optional, default: `20`)

## Boundaries and gotchas

- `--limit` must be at least 1.
- The 16-byte preview is diagnostic only and must not be interpreted as hidden meter values.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight mixer meter-settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
