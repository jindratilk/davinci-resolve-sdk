# `fairlight automation write`

Syntax: `cutagent fairlight automation write [LANE] [--value VALUE] [--track VALUE] [--clip VALUE] [--bus VALUE] [--at VALUE]`

## Search terms

- fairlight automation write
- Wrote an audio-clip volume-envelope point.
- fairlight automation write help
- fairlight automation write command

## What it does

Wrote an audio-clip volume-envelope point.

## Do not use when

Do not use this command for track-mixer or bus-mixer automation, pan, mute, plugin, send, EQ, or dynamics lanes; those mappings remain unavailable. `--bus` and `--clip` are rejected. Use `fairlight bus level` only for the separately mapped static Main output-gain field, and describe its limitations accurately.
Use `clip audio-gain` or `fairlight audio-gain batch` when the whole clip needs a constant gain change.

## Preflight and readback

Before writing, make the intended timeline active and confirm `--at` falls inside exactly one clip on the requested track. Create a checkpoint for important projects. Remember that relative frame input is converted to the timeline's record-frame domain.
Afterward, require the intended project and timeline—not `Untitled Project`—to reopen. Audition or render when audible parity is material.

## Public arguments and options

- `LANE` (optional) — Audio-clip automation lane; volume/level/gain are accepted
- `--value/-v` (optional) — Automation value to write
- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Unsupported; use --track with --at
- `--bus` (optional) — Unsupported for time-varying automation
- `--at` (optional) — Timeline timecode/frame/seconds for the automation write

## Boundaries and gotchas

- Both `--track` and `--at` are mandatory.
- Track numbering is one-based audio-track order.
- `--at` is parsed in timeline time, then converted to the record-frame domain by applying the timeline start offset.

## Examples

- `cutagent fairlight automation write --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
