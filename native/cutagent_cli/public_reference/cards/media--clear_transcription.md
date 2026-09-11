# `media clear-transcription`

Syntax: `cutagent media clear-transcription [--clip VALUE] [--folder VALUE]`

## Search terms

- clear Media Pool transcription
- remove source transcript
- delete speech analysis from clip
- clear all transcripts in bin
- reset transcription status
- remove auto transcription text
- erase DaVinci Resolve transcript
- clear current folder transcription

## What it does

Clear transcription for a clip and folder.

## Do not use when

Use subtitle/timeline text deletion when the artifact is a subtitle clip rather than Media Pool transcription metadata. Use clip mode when only one source should be cleared; folder/current mode can affect multiple items. Do not clear merely to rerun with another language until the old transcript has been recorded if it may be needed—there is no undo/export in this command.

## Preflight and readback

Resolve explicit folder paths rather than relying on current folder whenever scope matters. Re-transcribe only after confirming the correct objects were cleared.

## Public arguments and options

- `--clip/-c` (optional) — Clip name.
- `--folder/-f` (optional) — Folder path.

## Boundaries and gotchas

- `--clip` and `--folder` together are rejected, but both omitted is valid and targets the persistent current Media Pool folder.
- Dry-run labels an omitted target as current but does not connect, resolve current folder, or enumerate affected items.

## Examples

- `cutagent media clear-transcription --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
