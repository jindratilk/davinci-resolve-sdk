# `timeline subtitle export`

Syntax: `cutagent timeline subtitle export PATH [--format VALUE] [--track VALUE] [--all-tracks]`

## Search terms

- export timeline subtitles
- export caption track
- all subtitle tracks export
- subtitle timecode conversion

## What it does

Export subtitles.

## Do not use when

Do not use this command to export Fusion Text+, burned-in captions, subtitle styling, speaker/language metadata, or a rendered video with captions.
Do not combine multiple subtitle tracks unless a track-grouped, potentially overlapping flat file is acceptable. Rows are ordered by track then frame, not globally chronological, and cross-track identity is lost.

## Preflight and readback

Before execution, activate the correct timeline; list subtitle tracks/items; verify FPS/start frame, text, bounds, intended one/all-track scope, output parent, output format/suffix, and overwrite safety.
Verify timestamps, cue ordering, multiline text, overlaps, encoding, and that the extension matches the selected format.

## Public arguments and options

- `PATH` (required) — Output subtitle file
- `--format` (optional, default: `"srt"`) — srt, vtt, or ttml
- `--track` (optional) — Subtitle track index
- `--all-tracks` (optional, default: `false`) — Export all subtitle tracks

## Boundaries and gotchas

- `--track` and `--all-tracks` are mutually exclusive.
- Milliseconds are rounded from fractional seconds; the formatter does not explicitly normalize a rounded 1000 ms carry.
- It calculates bytes from the intended UTF-8 text but does not reopen/reparse the file.
- Verification does not compare against DaVinci Resolve UI, validate SRT/VTT syntax, or test importability.
- Dry-run does not validate subtitle-track availability, positive index, output parent/type, overwrite, text/timestamps, or file encoding.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent timeline subtitle export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
