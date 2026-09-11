# `project preset export`

Syntax: `cutagent project preset export NAME PATH`

## Search terms

- project preset export
- Export a project settings preset.
- project preset export help
- project preset export command

## What it does

Export a project settings preset.

## Do not use when

Do not choose an existing destination.

## Public arguments and options

- `NAME` (required) — Exact preset name
- `PATH` (required) — New export file path

## Boundaries and gotchas

- Preset matching is exact and case-sensitive; missing, duplicate, malformed, or ambiguous preset records fail closed.
- Names are preserved exactly, must be nonempty, contain no NUL byte, and are limited to 1024 characters.
- PATH must be bounded, its parent must already exist, and the target must be a new path.

## Examples

- `cutagent project preset export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
