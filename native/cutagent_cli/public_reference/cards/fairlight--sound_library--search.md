# `fairlight sound-library search`

Syntax: `cutagent fairlight sound-library search [QUERY] [--limit VALUE] [--database VALUE]`

## Search terms

- search Sound Library
- find indexed sound effect
- look up Foley by name
- find audio by tag
- locate library clip ID
- search project sound index
- search library by filename
- locate indexed WAV path
- find sounds in category
- search audio description
- look up Sound Library sync point
- find music bed in library

## What it does

Runs the public `fairlight sound-library search` CutAgent command.

## Do not use when

Use `fairlight sound-library source-list` when searching for indexed source directories and per-source row counts. A path query here returns individual clip rows and may repeat a container.
Use `index-file`/`index-folder` when no result exists because the audio has not been registered. Search does not discover files on disk or repair stale paths.
Prefer the returned exact clip/file ID over relying on a broad query or remembered result index.
Search is the safe readback step before delete; it never removes anything itself.
Do not use search as proof that a sound can be played.

## Preflight and readback

Form the query from the most discriminating known name, tag, category, path component or description. Use a limit large enough to expose ambiguity; dry-run is useful only to validate scope/query/limit plumbing, not actual matches.
After search, inspect `found`, `count`, `truncated`, result IDs and paths. If `truncated:true`, raise the limit or refine the term before selecting anything. Compare name, category, tags, file path, sample rate/duration and container path rather than choosing by name alone.
Before deletion, rerun the same search immediately and choose an exact current ID. Before source removal, switch to `source-list` to see the full container scope.
Then list the index or inspect sources before deciding whether to index new media; do not automatically create an entry just because one search was empty.

## Public arguments and options

- `QUERY` (optional) — Search query
- `--limit` (optional, default: `50`) — Maximum results to return, 1-500
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- `count` is only the number returned; no total-match count is calculated.
- A clip row may appear with null linked file/container data, and malformed duplicate cookies can broaden joins.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library search --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
