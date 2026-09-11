# `fairlight sound-library insert`

Syntax: `cutagent fairlight sound-library insert [QUERY] [--clip-id VALUE] [--file-id VALUE] [--result-index VALUE] [--limit VALUE] [--start-offset-samples VALUE] [--duration-samples VALUE] [--sync-to-playhead] [--sync-samples VALUE] [--restore-playhead] [--check-path] [--database VALUE]`

## Search terms

- put library sound on timeline
- add indexed audio at playhead
- place Foley hit on current audio track
- use Sound Library clip ID
- align sound effect sync point to playhead
- place impact so its hit lands at playhead
- add part of a library sound
- add Sound Library result to Fairlight track
- put tagged sound on timeline
- place one searched library asset
- sync a Foley transient to current frame

## What it does

Insert one project-indexed Sound Library file on the current Fairlight track.

## Do not use when

Use `fairlight sound-library search` first when a natural-language query may match several sounds. Do not use an arbitrary `--result-index` from an old search after the index changes.
Use the Media Pool/timeline clip insertion commands when the source is already a Media Pool item, when an explicit destination track is required, or when video must be inserted.
Use ordinary `--start-offset-samples` for a deliberate source trim whose beginning should sit at the playhead. Use `--sync-to-playhead` only when a source landmark should land at the playhead; the two modes are mutually exclusive because sync mode computes its own start offset near the timeline boundary.
Do not use `sound-library audition` or `preview` as an insertion substitute. Those commands report that panel preview/audition is unavailable; they do not create timeline media.
Use timeline move/slip/trim commands after insertion when placement needs frame-level correction, handles, fades or overlap resolution.

## Preflight and readback

Before insertion, ensure the intended project and timeline are active, switch to Fairlight if current-track identity depends on UI state, and inspect `timeline track list`. Confirm which audio track is current in DaVinci Resolve; the CLI cannot name it. Confirm the path is mounted and readable.
If the inserted item was only a test, delete that exact timeline item; deleting the Sound Library index row does not remove a timeline clip that was already inserted.

## Public arguments and options

- `QUERY` (optional) — Search query or known library result name
- `--clip-id` (optional)
- `--file-id` (optional)
- `--result-index` (optional) — 1-based result index when the query matches multiple rows
- `--limit` (optional, default: `50`) — Maximum DB search results to consider, 1-500
- `--start-offset-samples` (optional, default: `0`) — Sample offset within source media
- `--duration-samples` (optional, default: `0`) — Duration to insert in samples (0 = full available duration)
- `--sync-to-playhead/--no-sync-to-playhead` (optional, default: `false`)
- `--sync-samples` (optional)
- `--restore-playhead/--leave-playhead` (optional, default: `true`) — Restore the original playhead after a sync-to-playhead insert
- `--check-path/--no-check-path` (optional, default: `true`) — Require the resolved Sound Library file path to exist before calling DaVinci Resolve
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- Search ordering is name (case-insensitive), then clip ID.
- `--result-index` is 1-based in that current ordered result set.
- The ID must belong to a row also matching the query; an unrelated query can turn a valid ID into zero matches.
- Increase `--limit` or use an exact selector; otherwise hidden matches could make the choice unsafe.
- `--limit` is validated as 1–500.
- A too-small limit plus `--result-index` can make a valid later result appear out of range because only the limited set is considered.
- `--no-check-path` only bypasses this preflight; DaVinci Resolve can still reject an unmounted, stale or nonaudio path.
- `--sync-samples` is legal only with `--sync-to-playhead` and is constrained non-negative.
- `--restore-playhead` applies only to sync mode.
- The command does not copy the media.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
