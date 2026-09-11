# `fairlight solo-restore`

Syntax: `cutagent fairlight solo-restore --states-json VALUE`

## Search terms

- restore tracks after solo
- undo CutAgent solo
- restore previous audio enabled states
- un-solo Fairlight track safely
- recover mute states after audition
- restore A1 A2 track enable map
- return audio mix after isolated track
- reverse fairlight solo emulation
- re-enable tracks disabled by solo
- preserve original muted tracks
- restore track state JSON

## What it does

Restore audio tracks after solo mode.

## Do not use when

Use `fairlight unmute INDEX` or `mute INDEX` when intentionally changing one known track rather than restoring a captured set. Do not “restore” by enabling every track, because that loses any tracks that were muted before solo.
Do not use this as DaVinci Resolve's general undo.

## Preflight and readback

Before restoring, confirm the active timeline is exactly the one soloed and that audio track count/order has not changed. Compare current indices/names with the captured pre-solo context. Inspect the JSON manually: every row should have a unique integer index and a literal JSON boolean `true` or `false`.
Shell-quote the entire compact JSON array so quotes/braces survive argument parsing.
Switch back to the previously recorded page explicitly if the command opened Fairlight.
If any setter/readback fails, inspect all tracks before retrying.

## Public arguments and options

- `--states-json` (required) — JSON previous_states array from fairlight solo

## Boundaries and gotchas

- `--states-json` is required and must parse as a JSON array.
- Track name, timeline ID, stable track ID, or expected current state cannot protect against the wrong active timeline.
- The validator completes all row/type/index checks before the first write, so an out-of-range row prevents writes.
- A partial array is allowed and changes only its listed indices.
- Duplicate indices are not rejected.
- They are written in input order; conflicting duplicates leave the last value applied, then verification can fail because every duplicate row is compared with the final same-index state.
- It is not monitor-only.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight solo-restore --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
