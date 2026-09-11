# `workflow plugin info`

Syntax: `cutagent workflow plugin info PATH`

## Search terms

- workflow plugin manifest
- plugin info
- workflow integration metadata
- inspect plugin folder

## What it does

Check custom add-on details.

## Preflight and readback

Before execution, point to the plugin root. Afterward, inspect every manifest field yourself and run `workflow plugin validate`, Node/Python checks, packaging tests, and an actual DaVinci Resolve load smoke as appropriate.

## Public arguments and options

- `PATH` (required) — Plugin folder path

## Boundaries and gotchas

- Any nonempty valid JSON value is considered valid; required keys/types are not checked.
- Dry-run has no special branch and still reads/parses the manifest.

## Examples

- `cutagent workflow plugin info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
