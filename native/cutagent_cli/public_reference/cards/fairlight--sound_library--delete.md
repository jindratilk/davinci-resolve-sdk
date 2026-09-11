# `fairlight sound-library delete`

Syntax: `cutagent fairlight sound-library delete [QUERY] [--clip-id VALUE] [--file-id VALUE] [--file-path VALUE] [--result-index VALUE] [--limit VALUE] [--all] [--delete-orphan-file-row] [--delete-orphan-container-row] [--database VALUE]`

## Search terms

- remove Sound Library entry
- unindex sound effect
- delete Fairlight library row
- remove indexed audio by clip ID
- delete duplicate SFX index record
- clean orphan Sound Library rows
- delete indexed file metadata
- unlist audio file without deleting media
- remove all matching library results
- delete project Sound Library item
- clean stale Sound Library path

## What it does

Remove a Fairlight Sound Library entry.

## Do not use when

Use `fairlight sound-library source-remove` when intentionally removing every indexed row belonging to one source folder/path; it understands source/container scope. Use `source-rebuild` when an indexed source should be refreshed rather than removed.
This command intentionally leaves the file untouched.
Use `sound-library list` or `search` first when identity is ambiguous. Prefer an exact `--clip-id` for one index entry. A `--file-id` or path can correspond to multiple clip rows and therefore may require `--result-index` or deliberate `--all`.
Do not use it to remove a timeline occurrence or Media Pool clip.

## Preflight and readback

Record result count, truncation, clip/file/container IDs, path, references and source.
Prefer exact clip ID and avoid `--all` unless every returned row has been reviewed and `truncated:false`.
If parent rows were retained, confirm remaining reference counts and the dependent entries. Verify that the intended project reopened, not `Untitled Project`, and restore its timeline/page if needed.

## Public arguments and options

- `QUERY` (optional) — Search query or known library result name
- `--clip-id` (optional)
- `--file-id` (optional)
- `--file-path/--path` (optional) — Exact local file path to remove from the Sound Library index
- `--result-index` (optional) — 1-based result index when the selector matches multiple rows
- `--limit` (optional, default: `50`) — Maximum DB search results to consider, 1-500
- `--all` (optional, default: `false`) — Delete every matched index row; refuses truncated match sets
- `--delete-orphan-file-row/--keep-file-row` (optional, default: `true`)
- `--delete-orphan-container-row/--keep-container-row` (optional, default: `true`)
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- At least one of query, `--clip-id`, `--file-id`, or `--file-path` is required.
- `--all` cannot be combined with `--result-index` and refuses a truncated match set.
- Increase `--limit` or use exact IDs instead.
- `--limit` must be 1–500 and controls the search window.
- It is not a deletion-count cap once `--all` is accepted.
- `--keep-file-row` leaves the file row even when orphaned.
- `--keep-container-row` can intentionally leave an orphan container after an orphan file row is deleted.
- Parent deletion is based on remaining references, not only the selected row's apparent IDs.
- Choosing the wrong scope can delete a different library entry with similar metadata.
- Deleting an index row does not stop an audition, remove an already-inserted timeline clip, or invalidate copies of the media elsewhere.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
