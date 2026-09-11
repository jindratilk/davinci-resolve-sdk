# `media import`

Syntax: `cutagent media import PATH`

## Search terms

- import media file
- add footage to Media Pool
- bring audio into project
- ingest a local asset
- import a folder of clips
- add source file to bin
- load external media into DaVinci Resolve
- register a generated render in Media Pool
- import WAV video image or subtitle

## What it does

Import media into the media pool.

## Do not use when

Use `media append` when the asset is already in the Media Pool and the requested result is a timeline item. Use `timeline import` or the dedicated subtitle/timeline import command when the file represents a timeline interchange rather than ordinary source media. Use `media folders add` and `media move` when the job is bin organization; this command imports into the current folder and has no destination-folder option.

## Public arguments and options

- `PATH` (required) — File or folder path to import

## Boundaries and gotchas

- `~` is expanded, but the command does not canonicalize names, resolve duplicate sources, or choose a destination bin.
- Import does not deduplicate by source path or clip name.
- Existing same-name items can make later name-only commands ambiguous, especially when the copies land in different folders.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent media import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
