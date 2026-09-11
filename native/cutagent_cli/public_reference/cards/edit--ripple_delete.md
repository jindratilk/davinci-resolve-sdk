# `edit ripple-delete`

Syntax: `cutagent edit ripple-delete --at VALUE --duration VALUE [--fps VALUE] [--edl VALUE] [--name VALUE]`

## Search terms

- ripple delete timeline segment
- remove time and close gap
- cut interval from EDL
- shorten timeline by time range
- delete section and shift later clips left
- make new timeline without segment
- EDL-based ripple edit
- remove silence range through EDL
- close gap across all EDL events
- rewrite edit list after deletion
- create rippled timeline copy
- delete timecode interval non-destructively from original

## What it does

Remove a timeline segment and closed the gap.

## Do not use when

Use `edit remove-range` for a non-ripple lift, `edit remove` for one whole item, or `edit from-edl` when an EDL should be imported unchanged.
Do not use this as an in-place edit: it creates a separate timeline and switches current context. Do not use it without explicitly supplying the actual timeline/EDL FPS and an EDL-record-domain `HH:MM:SS:FF` start. Do not use it as a reliable media conform when `edit from-edl` cannot import the resulting EDL in the current project layout.

## Preflight and readback

Before execution, duplicate/checkpoint the project, export and inspect the original EDL, record the active timeline name/FPS/start timecode and inventory effects/tracks/audio/metadata that EDL cannot carry. Set `--fps` explicitly from that timeline.
Afterward, inspect the generated EDL line by line before import. Render across both cut boundaries and compare timeline duration. If import fails, preserve the generated EDL path as evidence and check for partial timelines/media before retrying.

## Public arguments and options

- `--at` (required) — Start timecode of segment to remove (HH:MM:SS:FF)
- `--duration` (required) — Duration to remove (e.g., '5s', '00:00:05:00', '125f')
- `--fps` (optional, default: `25.0`) — Timeline frame rate
- `--edl` (optional) — Use existing EDL instead of exporting
- `--name` (optional) — Name for the new timeline

## Boundaries and gotchas

- The default `--fps` is 25.0 and is never inferred from the active timeline, even when the command just exported that timeline.
- With no `--edl`, dry-run exits before parsing `--at` or connecting.
- With a provided EDL, dry-run goes much further: it reads/parses/rewrites the file and creates a real temporary output file before returning.
- At non-25 fps, frame-bearing event boundaries can be classified or shifted incorrectly even when `--fps` is correct.
- The command does not require that any event intersects the requested range.
- Only EDL-carried information survives.
- `--name` is used raw as EDL `TITLE:` but slashes, backslashes, colons and control separators are replaced with underscores only for the output filename.
- If import succeeds, it switches current timeline and does not restore the original timeline/playhead/selection.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit ripple-delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
