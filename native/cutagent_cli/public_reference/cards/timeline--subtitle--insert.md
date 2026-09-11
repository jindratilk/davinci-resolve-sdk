# `timeline subtitle insert`

Syntax: `cutagent timeline subtitle insert PATH [--ensure-track]`

## Search terms

- timeline subtitle insert
- Insert SRT subtitles as DaVinci Resolve subtitle-track items.
- timeline subtitle insert help
- timeline subtitle insert command

## What it does

Insert SRT subtitles as DaVinci Resolve subtitle-track items.

## Do not use when

Do not treat text-count verification as timing or placement proof.
Do not automatically retry after import/append/readback failure. The command can leave a created subtitle track, imported Media Pool item, and appended subtitle clips without cleanup.

## Preflight and readback

Check for imported Media Pool artifacts, newly created tracks, duplicate cues, and partial state after any error.

## Public arguments and options

- `PATH` (required)
- `--ensure-track/--no-ensure-track` (optional, default: `true`) — Create a subtitle track when none exists

## Boundaries and gotchas

- The file must exist and be a regular file.
- A block is accepted only when the first remaining line contains `-->`.
- At least one accepted timed nonempty-text entry is required.
- `--no-ensure-track` fails when there are zero tracks.
- For each exact expected text, only the positive count delta is credited.
- Duplicate expected texts are handled by counts.
- Verification does not compare the parsed timing strings at all.
- It does not verify destination track, start/end, order, formatting, or absence of extra appended rows.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline subtitle insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
