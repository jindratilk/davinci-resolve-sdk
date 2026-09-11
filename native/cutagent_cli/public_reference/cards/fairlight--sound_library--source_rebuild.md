# `fairlight sound-library source-rebuild`

Syntax: `cutagent fairlight sound-library source-rebuild FOLDER [--recursive] [--max-files VALUE] [--name-prefix VALUE] [--category VALUE] [--description VALUE] [--tag VALUE] [--rating VALUE] [--allow-duplicate] [--database VALUE]`

## Search terms

- rebuild Sound Library source
- rescan indexed audio folder
- replace stale Sound Library entries
- synchronize Sound Library folder index
- delete and reindex SFX folder
- remove missing sounds and add new ones
- rebuild nested Foley source
- refresh project Sound Library metadata
- reindex folder with new tags
- replace Sound Library clip IDs
- reset source metadata from current files

## What it does

Delete and rebuild one Fairlight Sound Library source folder in the selected project index.

## Do not use when

Use `fairlight sound-library index-folder` for additive scanning that should preserve all existing source rows and IDs.
Use `source-remove` when the folder should disappear from the index with no rescan. Use individual `sound-library delete` when only selected clip rows should be removed and other source members/IDs preserved.
Source-rebuild replaces every matched container/file/clip relation in scope.
Use `source-list` plus `search/list` before rebuild when the path, nested scope, counts or metadata are unclear.
Do not use rebuild merely to change one tag/name/rating if stable clip/file IDs matter.
Do not choose a low `--max-files` as pagination. The command can delete the entire matched source scope and rebuild only the first capped paths.

## Preflight and readback

Before rebuilding, confirm project versus user scope and active project. Run source-list exact and recursive, then search/list all affected member rows; preserve old IDs, paths, metadata and counts. Inspect the disk folder independently, decide recursive scope, and run dry-run with the final max-files.
Review the shared prefix/category/description/tags/rating.
Confirm expected physical files still exist, stale paths are absent, and unrelated sources remain.
If some candidates were skipped, inspect each reason and verify whether the old record was deleted. A mixed readable/unreadable batch can succeed while leaving unreadable files unindexed.

## Public arguments and options

- `FOLDER` (required) — Local Sound Library source folder to delete from the DB index and rescan
- `--recursive/--no-recursive` (optional, default: `true`) — Rescan nested folders and clear nested indexed source paths
- `--max-files` (optional, default: `200`)
- `--name-prefix` (optional) — Optional prefix for generated Sound Library clip names
- `--category` (optional) — Optional Sound Library category for all indexed files
- `--description` (optional) — Optional searchable description for all indexed files
- `--tag` (optional, repeatable) — Optional searchable user tag; repeat up to four times
- `--rating` (optional, default: `0`) — Star rating metadata, 0-5
- `--allow-duplicate` (optional, default: `false`) — Allow additional Sound Library rows for file paths already indexed elsewhere
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- `--no-recursive` limits both halves to the exact folder/direct children.
- `--max-files` truncates disk discovery but does **not** narrow deletion to the same file set.
- The entire exact/recursive source scope is removed, then only the first selected paths are reinserted.
- If at least one candidate is readable, rebuild proceeds: old scope rows are deleted and unreadable candidates remain only in `skipped`.
- Dry-run never probes audio streams.
- Existing source rows are deleted before duplicate checks.
- Therefore a same-path row inside the rebuild scope is not considered a duplicate; `--allow-duplicate` matters only for matching paths still indexed outside the deleted scope.
- The source may therefore lose its old in-scope record while the other source's record remains.
- With `--allow-duplicate`, another complete container/file/clip triplet is created; records are not shared or merged.
- Source deletion refuses more than 500 grouped matched source paths even though `--max-files` can be as high as 5000.
- Audio metadata uses the first stream only.
- When new rows exist, verification checks their IDs/paths but does not separately assert every old ID is absent.
- Perform old-ID/name searches after the command, especially for mixed duplicate/skip cases.
- When no row is inserted, verification checks source-scope absence; this can be correct even though equivalent physical paths remain indexed under other containers.
- Project scope closes/reopens the project.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library source-rebuild --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
