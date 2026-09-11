# `edit auto-subtitle`

Syntax: `cutagent edit auto-subtitle [--language VALUE] [--preset VALUE] [--chars-per-line VALUE] [--line-break VALUE] [--gap VALUE]`

## Search terms

- automatically subtitle timeline
- create captions from audio
- transcribe speech into subtitles
- auto caption video
- generate subtitle track from dialogue
- speech to captions in DaVinci Resolve
- add Netflix-style auto captions
- create subtitles from timeline audio
- caption interview automatically
- transcribe all timeline audio
- make captions with line length
- auto-generate SRT-style timeline captions

## What it does

Create subtitles from timeline audio.

## Do not use when

Use subtitle add/import commands when text and timings are already known, and subtitle export only after captions exist. Use media transcription commands when the goal is searchable Media Pool transcription rather than timeline subtitle clips.
Do not use this command for one selected audio track, clip or marked range—it targets the active timeline as a whole and exposes no track/range selector. Do not use it when captions must preserve a reviewed existing subtitle track without first making a timeline/project checkpoint.

## Preflight and readback

In DaVinci Resolve's GUI, verify auto-caption works and required Studio/Extras language assets are installed. Choose explicit options if UI/project defaults are not acceptable.
Afterward, independently list subtitle tracks/items and inspect caption text, language, timing, line breaks, gaps and overlap with existing captions. Export SRT/VTT for textual review and compare representative dialogue.

## Public arguments and options

- `--language` (optional) — auto|english|german|...
- `--preset` (optional) — default|teletext|netflix
- `--chars-per-line` (optional)
- `--line-break` (optional) — single|double
- `--gap` (optional) — Gap between captions in frames/seconds per DaVinci Resolve setting

## Boundaries and gotchas

- Presets are only default, teletext and netflix; line-break modes are single/double.
- The SDK documents 42 chars/line generally, but, for example, Korean plus Netflix defaults to 16; an empty/partial dictionary does not imply fixed values.

## DaVinci Resolve editions

In DaVinci Resolve's GUI, verify auto-caption works and required Studio/Extras language assets are installed.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit auto-subtitle --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
