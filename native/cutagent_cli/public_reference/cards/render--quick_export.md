# `render quick-export`

Syntax: `cutagent render quick-export PRESET [--output VALUE]`

## Search terms

- quick export render
- Quick Export preset selector
- export current timeline
- one-click Deliver preset
- render preset by index
- DaVinci Resolve 20 quick export
- synchronous quick export result

## What it does

Render using a quick export preset.

## Do not use when

Do not use this when you need full control over queue jobs, render ranges, codecs, filenames, or advanced Deliver settings; use the normal render settings and queue commands.
Do not use a partial preset selector when multiple Quick Export presets have similar names.

## Preflight and readback

After execution, inspect the returned file, confirm duration, streams, codec, resolution, audio, subtitles, and visual content, and compare it with the intended current timeline.

## Public arguments and options

- `PRESET` (required) — Quick export preset name.
- `--output/-o` (optional) — Output directory.

## Boundaries and gotchas

- `-o` is the short alias for `--output`.
- Match order is exact, unique case-insensitive, unique punctuation-insensitive normalized, positive 1-based index, then unique normalized substring.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent render quick-export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
