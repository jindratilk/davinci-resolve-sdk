# `fairlight sound-library index-file`

Syntax: `cutagent fairlight sound-library index-file PATH [--name VALUE] [--category VALUE] [--description VALUE] [--tag VALUE] [--rating VALUE] [--allow-duplicate] [--database VALUE]`

## Search terms

- add file to Sound Library
- index one sound effect
- register local WAV in Fairlight
- make audio searchable in Sound Library
- import SFX into library index
- add local audio metadata
- register dialogue file in project library
- catalog one music file
- add tags and rating to Sound Library
- index audio without inserting timeline clip
- register sound by file path
- add searchable audio asset

## What it does

Add a Fairlight Sound Library file.

## Do not use when

Use `sound-library index-folder` for a folder/batch scan; it discovers supported extensions, applies a maximum file count and can skip existing paths together. Use `source-rebuild` when replacing all indexed rows for one source folder.
Indexing alone creates no timeline or Media Pool item. Use the visible Sound Library panel for audition; CLI audition is unsupported.
It creates another full container/file/clip set for the same physical path rather than editing the existing row.

## Preflight and readback

Review normalized name/category/description/tags/rating with dry-run.

## Public arguments and options

- `PATH` (required) — Local audio file path to register in the selected Sound Library index
- `--name` (optional) — Sound Library clip name; defaults to file stem
- `--category` (optional) — Optional Sound Library category
- `--description` (optional) — Optional searchable description
- `--tag` (optional, repeatable) — Optional searchable user tag; repeat up to four times
- `--rating` (optional, default: `0`) — Star rating metadata, 0-5
- `--allow-duplicate` (optional, default: `false`) — Allow another Sound Library row for the same file path
- `--database/--db` (optional, default: `"project"`) — Sound Library DB scope: project/current-project or user/local-database

## Boundaries and gotchas

- Dry-run still requires the path to exist and be a file, because path validation occurs before the dry-run branch.
- Without `--allow-duplicate`, any result aborts before inserts.
- `--allow-duplicate` creates new container, file and clip UUIDs even when the path is identical.
- It does not reuse an existing file/container or merge metadata.
- Audio metadata comes from the first audio stream only.
- Multi-stream files do not create multiple library clips.
- Project scope closes and reopens the project.
- Indexing does not verify that DaVinci Resolve's visible Sound Library panel refreshed or can audition the row.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight sound-library index-file --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
