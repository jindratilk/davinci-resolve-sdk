# `fairlight sound-library list`

Syntax: `cutagent fairlight sound-library list [--query VALUE] [--limit VALUE] [--database VALUE]`

## Search terms

- list Sound Library entries
- show indexed sounds
- browse Fairlight audio library
- enumerate project sound effects
- list indexed audio paths
- view Sound Library metadata
- find Sound Library clip IDs
- inventory registered Foley
- show library tags and ratings
- inspect indexed sync points
- see what sounds are cataloged
- browse project audio index

## What it does

Runs the public `fairlight sound-library list` CutAgent command.

## Do not use when

Use `fairlight sound-library search QUERY` when a query is mandatory and should be supplied positionally.
Use `fairlight sound-library source-list` when the question is which source/container directories are indexed and how many clip/file rows each source has. `list` returns one entry per clip join and can repeat the same container path many times.
Use `fairlight sound-library index-file` or `index-folder` to add absent entries. Use `delete`, `source-remove` or `source-rebuild` to change the index. `list` never repairs stale paths or reconciles disk contents.
Listing produces identifiers and path evidence but no timeline mutation.
Do not use this command to inventory Media Pool clips or timeline audio.

## Preflight and readback

Before listing, identify the intended scope.
If `truncated:true`, do not treat the page as the whole library; narrow the query or raise the limit up to 500.
For stale-media diagnosis, independently check returned paths on disk. `found:true` means an index row exists, not that the file is mounted or readable.

## Public arguments and options

- `--query/-q` (optional) — Optional search filter
- `--limit` (optional, default: `50`) — Maximum results to return, 1-500
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- The default does not merge them.
- `count` is only the returned page size.
- A blank/whitespace query becomes no filter, so `--query " "` lists the index rather than returning no matches.
- A clip row can be returned with null nested file/container fields; `found:true` does not guarantee a usable insertion path.
- Do not present them as interpreted settings without the owning command's conversion contract.
- It does not close/reopen the project for this read.
- Those paths are diagnostic context and must not be treated as portable product requirements.

## Examples

- `cutagent fairlight sound-library list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
