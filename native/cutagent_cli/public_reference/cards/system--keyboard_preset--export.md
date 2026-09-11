# `system keyboard-preset export`

Syntax: `cutagent system keyboard-preset export NAME PATH`

## Search terms

- system keyboard-preset export
- Export one keyboard preset without replacing a file.
- system keyboard-preset export help
- system keyboard-preset export command

## What it does

Export one keyboard preset without replacing a file.

## Do not use when

This command never replaces an existing file.

## Preflight and readback

Capture the active preset and ordered catalog before export.

## Public arguments and options

- `NAME` (required) — Exact preset name
- `PATH` (required) — New export file path

## Boundaries and gotchas

- The output must be a non-empty regular file no larger than 16 MiB.
- Installation uses a new-file-only operation and fails if another process creates the target concurrently.

## Examples

- `cutagent system keyboard-preset export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
