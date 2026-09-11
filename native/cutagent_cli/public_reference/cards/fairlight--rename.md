# `fairlight rename`

Syntax: `cutagent fairlight rename INDEX NAME`

## Search terms

- rename Fairlight track
- change audio track name
- label A1 Dialogue
- rename audio lane
- set audio track label
- organize Fairlight tracks by name
- change track header text
- rename voiceover track
- relabel timeline audio track
- name A2 sound effects

## What it does

Rename an audio track.

## Do not use when

`fairlight rename` always targets audio.
Use clip rename/display-name or Media Pool rename commands when the user means one clip occurrence or its source media. A track label does not propagate into clip names, filenames, reel/tape metadata, render names, or source metadata.
Use bus/Main/VCA/group commands when the requested label belongs to a mixer object rather than an audio track. Do not rename a track as a substitute for assigning it to a bus or group.
Do not use it to reorder tracks or make “A2 become A1”; names do not change indices. Use track structural commands for insertion/deletion/reordering behavior, with appropriate caution.

## Preflight and readback

Before renaming, run `timeline track list`, `fairlight tracks`, or `fairlight info INDEX`. Confirm the active timeline, 1-based audio index, current name, clip count, format, and any downstream automation/scripts that address tracks by name.
Dry-run can confirm the literal index/name request, but it does not check track existence, current name, duplicate labels, or DaVinci Resolve's acceptance.
After success, use `timeline track list` or `fairlight info INDEX` and require the exact returned name on the same audio index. Also confirm item count and neighboring track identities if name-based selectors are used downstream.

## Public arguments and options

- `INDEX` (required) — Track index
- `NAME` (required) — New name

## Boundaries and gotchas

- The command hard-codes `audio`; it cannot rename video or subtitle tracks.
- The CLI does not trim whitespace, normalize Unicode, constrain length, reject control characters, or prevent duplicate track names.
- Names containing spaces or shell-special characters must be quoted correctly.
- It does not include index/name as structured fields, old name, stable track ID, or affected item count.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
