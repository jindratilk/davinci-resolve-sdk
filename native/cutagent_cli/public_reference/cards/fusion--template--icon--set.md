# `fusion template icon set`

Syntax: `cutagent fusion template icon set TEMPLATE PNG [--overwrite]`

## Search terms

- set Fusion template icon
- add PNG beside setting
- template thumbnail
- Fusion icon PNG
- install template icon
- replace template icon
- template icon dry-run
- Resolve template thumbnail
- adjacent .png

## What it does

Set a Fusion template icon.

## Do not use when

Do not use an unreviewed image or trust the extension alone. The command does not decode PNG content, check dimensions, color space, alpha, file size, or DaVinci Resolve thumbnail requirements.
Do not overwrite an existing icon without backing it up.
Do not pass the icon target itself as the PNG source with `--overwrite`.
Do not rely on bare-name search when the same template name exists in multiple kinds. The first Titles/Generators/Effects/Transitions match wins without ambiguity reporting.
Do not expect the command to refresh DaVinci Resolve or prove that the icon appears in the Effects Library.

## Preflight and readback

Explicitly confirm source and destination differ.
For cleanup, restore a backed-up prior icon or remove only the newly created adjacent PNG. Preserve/remove the template and source according to their own workflows.

## Public arguments and options

- `TEMPLATE` (required) — Template name or path
- `PNG` (required) — PNG icon path
- `--overwrite` (optional, default: `false`) — Replace an existing icon

## Boundaries and gotchas

- `--overwrite` is optional.
- Search returns the first match and does not report ambiguity.
- The command does not refresh or inspect DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template icon set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
