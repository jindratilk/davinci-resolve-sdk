# `version list`

Syntax: `cutagent version list [--project-name VALUE] [--timeline-name VALUE] [--session-id VALUE]`

## Search terms

- list project checkpoints
- checkpoint history
- filter checkpoint session
- filter project versions
- timeline checkpoint records
- version.checkpoint inventory

## What it does

List project checkpoints.

## Do not use when

Do not expect fuzzy, case-insensitive, partial, or whitespace-normalized filters.

## Public arguments and options

- `--project-name` (optional) — Filter by DaVinci Resolve project name
- `--timeline-name` (optional) — Filter by DaVinci Resolve timeline name
- `--session-id` (optional) — Filter by CutAgent session id

## Boundaries and gotchas

- They are case-sensitive and not trimmed or normalized.
- Duplicate ids are not collapsed.
- Only dictionary records with string ids survive index loading.
- Global dry-run has no special branch and performs the same local index read/filter.

## Examples

- `cutagent version list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
