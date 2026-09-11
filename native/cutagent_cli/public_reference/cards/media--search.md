# `media search`

Syntax: `cutagent media search QUERY [--exact] [--kind VALUE] [--include-generated]`

## Search terms

- search entire Media Pool
- find clip by partial name
- locate asset in bins
- find duplicate clip names
- search timeline entries
- locate source file folder
- find non-generated media
- case-insensitive clip search

## What it does

Search for clips in the entire media pool.

## Do not use when

Use `media list` when browsing only the current folder/subtree without a name query. Do not use partial search output as an edit target until duplicates are resolved by folder/source path. Use dedicated metadata search only when matching property values rather than item names; this command searches names only.

## Preflight and readback

Start with a distinctive case-insensitive fragment and appropriate `--kind`; inspect all result folders/paths. When the exact spelling is known, rerun with `--exact` to prove identity.

## Public arguments and options

- `QUERY` (required) — Search query
- `--exact` (optional, default: `false`) — Exact name match
- `--kind` (optional) — Filter by kind: media, timeline, subtitle
- `--include-generated/--exclude-generated` (optional, default: `true`)

## Boundaries and gotchas

- Search always begins at Media Pool root, unlike `media list --recursive`, which begins at the current folder.
- Query is matched only against item name—not source path, folder, metadata, notes, or codec.
- `--kind` is inferred (`media`, `timeline`, `subtitle`) and rejects other values.
- `--exclude-generated` relies on the same name/type heuristic as media list, not a definitive DaVinci Resolve generated flag.

## Examples

- `cutagent media search --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
