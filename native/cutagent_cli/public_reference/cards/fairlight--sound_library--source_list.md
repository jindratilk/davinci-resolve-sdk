# `fairlight sound-library source-list`

Syntax: `cutagent fairlight sound-library source-list [--path VALUE] [--recursive] [--limit VALUE] [--database VALUE]`

## Search terms

- list Sound Library source folders
- show indexed audio directories
- inspect library container paths
- list Fairlight sources
- find Sound Library root folders
- count indexed files by folder
- show nested library sources
- check whether source folder is online
- inspect project Sound Library directories
- find stale Sound Library folders
- inspect source before rebuild
- verify source before removal

## What it does

List indexed Fairlight Sound Library source and container paths.

## Do not use when

Use `fairlight sound-library list` or `search` when the desired unit is an individual indexed clip/file with name, tags, rating, audio/edit metadata or exact IDs.
Use `fairlight sound-library source-remove` when the user explicitly wants every index row for an exact source path (and optionally descendants) removed. Run this card's command first to prove the matched paths/counts; source-list itself never deletes.
Source-list can show current grouped coverage and online status but does not detect which individual files were added/removed.
Use `index-file` for one known file. A source existing on disk but absent from these aggregates is not registered merely by listing it.
Do not use a physical audio filename as `--path`.
Do not treat this as DaVinci Resolve's separate UI source-preference list.

## Preflight and readback

Choose a limit high enough to avoid hiding sources.
If `truncated:true`, narrow the root or increase the limit before using the result to plan `source-remove` or `source-rebuild`.
Immediately before a source mutation, rerun the same exact path/recursive/scope combination. After mutation, rerun source-list and individual search/list to prove the intended aggregate disappeared or was rebuilt, while unrelated sources remain.

## Public arguments and options

- `--path/--source` (optional) — Optional source/container path to inspect
- `--recursive/--no-recursive` (optional, default: `true`) — When --path is set, include nested indexed source paths
- `--limit` (optional, default: `100`) — Maximum source rows to return, 1-500
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- With no `--path`, the `recursive` flag is present in output but has no filtering effect; all sources are listed either way.

## Examples

- `cutagent fairlight sound-library source-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
