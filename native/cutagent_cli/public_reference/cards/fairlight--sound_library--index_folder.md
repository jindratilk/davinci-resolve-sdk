# `fairlight sound-library index-folder`

Syntax: `cutagent fairlight sound-library index-folder FOLDER [--recursive] [--max-files VALUE] [--name-prefix VALUE] [--category VALUE] [--description VALUE] [--tag VALUE] [--rating VALUE] [--allow-duplicate] [--database VALUE]`

## Search terms

- add folder to Sound Library
- index sound effects folder
- scan audio folder into Fairlight
- make a Foley library searchable
- batch register local audio
- import SFX folder into Sound Library index
- recursively index audio files
- add music folder to project library
- register nested sound folders
- build Sound Library entries from files
- tag a batch of Sound Library sounds
- scan a folder without importing timeline clips

## What it does

Add a Fairlight Sound Library folder.

## Do not use when

Use `fairlight sound-library index-file` when registering exactly one known file and when an already-indexed path should be a hard validation error rather than a batch skip. `index-file` also permits an explicit complete `--name`; `index-folder` only produces `name-prefix + stem`.
Use `source-list` to inspect indexed container paths.
Folder indexing creates search records only. It neither populates the Media Pool nor chooses a timeline destination.

## Preflight and readback

If the command reports `truncated:true`, continue intentionally with a narrower subfolder or a reviewed higher limit; repeating the same capped scan will revisit the same first paths.
If the purpose was a repeatable synchronization rather than additive indexing, compare disk contents with `source-list`/`search`, then use `source-rebuild` only after reviewing its deletion scope.

## Public arguments and options

- `FOLDER` (required) — Local folder containing audio files to register in the selected Sound Library index
- `--recursive/--no-recursive` (optional, default: `true`) — Scan nested folders for supported audio files
- `--max-files` (optional, default: `200`)
- `--name-prefix` (optional) — Optional prefix for generated Sound Library clip names
- `--category` (optional) — Optional Sound Library category for all indexed files
- `--description` (optional) — Optional searchable description for all indexed files
- `--tag` (optional, repeatable) — Optional searchable user tag; repeat up to four times
- `--rating` (optional, default: `0`) — Star rating metadata, 0-5
- `--allow-duplicate` (optional, default: `false`) — Allow additional Sound Library rows for file paths already indexed
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- Indexing does not create a video-aware library object.
- Files are sorted by canonical full path using case-folded text, then sliced at `--max-files`.
- Re-running unchanged with the same cap does not progress to the next page.
- `--max-files` is constrained to 1–5000 and defaults to 200.
- Duplicate detection is per exact canonical file path and case-insensitive in SQL.
- Without `--allow-duplicate`, duplicates are skipped while other files can still be inserted.
- `--name-prefix` is concatenated directly with the stem; no separator is added.
- Audio metadata comes from the first audio stream only.
- Project scope closes and reopens the project.
- Do not infer user-scope behavior from a project-scope path alone.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library index-folder --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
