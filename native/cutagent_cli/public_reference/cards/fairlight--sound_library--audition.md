# `fairlight sound-library audition`

Syntax: `cutagent fairlight sound-library audition [QUERY] [--clip-id VALUE] [--file-id VALUE] [--result-index VALUE] [--sync-to-playhead] [--database VALUE]`

## Search terms

- audition Sound Library effect
- preview sound effect without inserting
- listen to door slam result
- play indexed audio before using it
- hear Sound Library clip
- sync preview to playhead
- preview local Sound Library file
- listen to search result index
- audition by clip ID
- audition by file ID
- stop Sound Library preview
- inspect preview playback state

## What it does

Audition a Fairlight Sound Library result.

## Do not use when

Use DaVinci Resolve's visible Fairlight Sound Library panel to audition a result without changing the timeline.
Use `fairlight sound-library list` or `search` when the task is to discover indexed rows and metadata.
Use a normal file/audio player outside DaVinci Resolve only when panel routing/sync is unnecessary and the resolved local file path is already known and authorized. This CLI command does not resolve the path for you.
Do not use `--sync-to-playhead` expecting the playhead to move or preview to start.

## Preflight and readback

For a real manual audition, first search the correct project/user library, disambiguate the result by name/path/ID, verify monitoring level/output, and use the visible panel. Confirm that no timeline item is inserted and that preview stops when requested.
If choosing insertion after audition, separately capture the active timeline, current Fairlight track, playhead, result IDs, local path, sync marker and item count.
After this CLI command fails, no project verification is necessary because it performs no read/playback/write. Do not interpret echoed selectors as a matched result.

## Public arguments and options

- `QUERY` (optional) — Search query or known library result name to audition
- `--clip-id` (optional)
- `--file-id` (optional)
- `--result-index` (optional) — 1-based result index when the selector matches multiple rows
- `--sync-to-playhead/--no-sync-to-playhead` (optional, default: `false`) — Request Sound Library panel sync-preview behavior when available
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- Query, `--clip-id`, `--file-id`, and `--result-index` are not cross-validated or resolved.
- Supplying all of them only echoes them.
- `--sync-to-playhead` is `true`; `--no-sync-to-playhead` and omission are both `false`.
- The command cannot report audition duration, current position, monitoring bus, volume, loop state, waveform, or whether a file is missing.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library audition --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
