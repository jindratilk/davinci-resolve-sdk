# `storage import`

Syntax: `cutagent storage import PATH`

## Search terms

- import from Media Storage
- add media to Media Pool
- import file or folder
- MediaStorage import path
- current Media Pool folder
- bulk folder import
- imported item count

## What it does

Import media from storage into the media pool.

## Do not use when

Do not run without confirming the exact active project and current Media Pool destination folder.
Do not trust dry-run to validate path existence, type, readability, supported media, or import scope.

## Preflight and readback

Before execution, inspect the source path with local tools and `storage files`, make the intended Media Pool bin current, capture existing bin contents, and use a unique test asset when verifying behavior.
Compare actual count with the success message.

## Public arguments and options

- `PATH` (required) — File/folder path to import

## Boundaries and gotchas

- The CLI does not expand `~`, resolve relative paths, normalize separators, or convert to absolute paths.
- It does not check whether the path exists.
- Importing can create duplicate Media Pool items.
- The command does not append imported media to a timeline.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent storage import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
