# `render transcript-audio`

Syntax: `cutagent render transcript-audio OUTPUT_PATH [--preset-path VALUE] [--preset-name VALUE]`

## Search terms

- render transcript audio
- CutAgent Transcript preset
- temporary MP3 render preset
- preserve render queue jobs
- restore Deliver context
- transcript-ready MP3
- active timeline audio export

## What it does

Render transcript-ready audio from the active timeline.

## Do not use when

Do not run while another render is active; the workflow deliberately refuses to interrupt it.
Do not use a non-MP3 destination or an untrusted/unreviewed preset XML.
Do not rely on this as a lossless archival audio export; it intentionally targets MP3 transcription audio.

## Preflight and readback

Capture `render settings`, format/codec, mode, current page, and the preset list.
Use the bundled source preset unless a custom XML has been inspected.
After execution, verify the returned path is a newly created playable MP3 with expected duration, sample properties, channel content, and timeline audio. Confirm original queue jobs remain, the temporary job and unique preset are gone, the previous page/settings/mode/format were restored, and no temp bundle remains.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output transcript audio file path
- `--preset-path` (optional) — Path to transcript render preset XML
- `--preset-name` (optional, default: `"CutAgent Transcript"`) — Imported render preset name

## Boundaries and gotchas

- Dry-run does not validate the preset name, XML structure, output parent, overwrite state, project, timeline, queue, or active render.
- If render starts but does not complete, cleanup repeatedly attempts global stop and then deletes the temporary job.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent render transcript-audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
