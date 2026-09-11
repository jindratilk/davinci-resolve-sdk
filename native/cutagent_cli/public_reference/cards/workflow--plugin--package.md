# `workflow plugin package`

Syntax: `cutagent workflow plugin package PATH --output VALUE [--overwrite]`

## Search terms

- package workflow plugin
- plugin zip archive
- workflow integration distribution
- zip plugin folder

## What it does

Package a custom add-on.

## Do not use when

Do not use this as plugin validation, signing, notarization, reproducible packaging, dependency bundling, or proof the package can be installed.

## Preflight and readback

Before execution, validate and inspect the source, choose an output outside the source identity, and preserve an existing archive unless overwrite is intended. Afterward, inspect archive members, test extraction/install, and distribute through the required secure channel.

## Public arguments and options

- `PATH` (required) — Plugin folder path
- `--output` (required) — Output zip path
- `--overwrite` (optional, default: `false`) — Replace an existing package file

## Boundaries and gotchas

- Exact syntax is `cutagent workflow plugin package PATH --output ZIP [--overwrite]`.

## Examples

- `cutagent workflow plugin package --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
