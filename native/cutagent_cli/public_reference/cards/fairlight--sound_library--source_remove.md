# `fairlight sound-library source-remove`

Syntax: `cutagent fairlight sound-library source-remove SOURCE_PATH [--recursive] [--database VALUE]`

## Search terms

- remove Sound Library source
- unindex audio folder
- delete library folder entries
- clear indexed source path
- remove all library clips under folder
- forget Sound Library source
- clean stale indexed folder
- remove nested library sources
- delete project Sound Library source
- unlist a Sound Library folder
- purge source metadata without deleting files

## What it does

Remove all Fairlight Sound Library project index rows for one indexed source path.

## Do not use when

Use `fairlight sound-library delete` to remove one or a selected set of individual clip rows while optionally retaining shared file/container rows. `source-remove` deletes every clip/file/container linked to the matched source containers.
Use `fairlight sound-library source-rebuild` when the source should remain indexed but be refreshed from current disk contents.
Use `fairlight sound-library source-list` first when path identity or descendant scope is uncertain. Compare exact `--no-recursive` with `--recursive`; never infer mutation scope from the physical folder tree alone.
Use `index-folder` when the user only wants to add newly discovered files without clearing any source rows. Use a file-management command when the request is to delete/move the actual audio files; source-remove deliberately preserves them.
Do not use this command to remove timeline clips or Media Pool references. Those are separate objects and can remain after the Sound Library index entry disappears.
Do not target a file path.

## Preflight and readback

Run `sound-library search` on those paths to capture individual IDs and check for shared/legacy relationships.
Rerun source-list with the identical path/scope/recursive flag and separately list/search unrelated sources to prove isolation. Check physical files still exist and verify any timeline/Media Pool objects expected to remain.

## Public arguments and options

- `SOURCE_PATH` (required) — Indexed Sound Library source/container folder path to remove from the DB index
- `--recursive/--no-recursive` (optional, default: `false`) — Also remove nested indexed source paths
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- Rows with missing IDs can be counted by joins but cannot be put into the deletion ID set, which may lead verification to fail if their source remains.
- Recursive scope uses case-insensitive exact-or-`path/%` SQL matching.
- Windows indexes storing backslash-only paths may not match nested containers as expected; inspect `source-list` output before mutation.
- Both-blank containers are outside source-remove scope.
- Verification rechecks only up to 20 remaining source rows in the exact/recursive scope.
- Any remaining row makes it fail; it does not individually re-query every returned deleted ID.
- Removing the index does not break or delete already-inserted timeline items immediately, but those items and future relinks still depend on the physical media path.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library source-remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
