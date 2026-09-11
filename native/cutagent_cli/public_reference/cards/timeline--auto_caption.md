# `timeline auto-caption`

Syntax: `cutagent timeline auto-caption [--language VALUE] [--preset VALUE] [--chars-per-line VALUE] [--line-break VALUE] [--gap VALUE]`

## Search terms

- create subtitles from audio
- DaVinci Resolve auto caption
- speech to subtitle track
- Netflix caption preset
- subtitle language setting
- caption characters per line
- auto transcription captions

## What it does

Create subtitles from timeline audio using DaVinci Resolve auto-caption.

## Do not use when

Do not use this command for designed Text+ captions, custom transcript segmentation, or an external transcript file.
Do not run it when the active timeline, included audio, language model/license, or existing subtitle state is ambiguous. The command operates on the active timeline as a whole and exposes no audio-track, range, or target-subtitle-track selector.
Review language, timing, wording, line breaks, gaps, and every generated caption.

## Preflight and readback

Record current subtitle track/item counts.
Export SRT/VTT or render representative sections for independent timing/text proof. Manually remove unwanted generated tracks/items.

## Public arguments and options

- `--language` (optional) — auto|english|german|...
- `--preset` (optional) — default|teletext|netflix
- `--chars-per-line` (optional)
- `--line-break` (optional) — single|double
- `--gap` (optional) — Gap between captions in frames/seconds per DaVinci Resolve setting

## Boundaries and gotchas

- No option selects audio tracks, an in/out range, speakers, an existing transcript, or a destination subtitle track.
- Characters per line must be 1 through 60.
- Gap must be an integer from 0 through 10.
- It rejects only an exact audio track count of zero.
- Success output does not include generated text, item IDs, target track identity, audio item count, or full preflight.
- The command does not delete or replace existing subtitles first.
- Dry-run omits every requested option.
- Dry-run does not connect, inspect audio/subtitles, resolve constants, or normalize language/preset/line-break values.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline auto-caption --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
