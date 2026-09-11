# `project db restore`

Syntax: `cutagent project db restore PATH --name VALUE --dir VALUE`

## Search terms

- project db restore
- Restore a project backup.
- project db restore help
- project db restore command

## What it does

Restore a project backup.

## Preflight and readback

After success, inspect representative projects and outputs before promotion.

## Public arguments and options

- `PATH` (required) — Backup file path
- `--name` (required) — Explicit target project-library name
- `--dir` (required) — Explicit new target project-library directory

## Boundaries and gotchas

- `--name` and `--dir` are required; there are no target defaults.
- The destination must not exist and is never overwritten.

## Examples

- `cutagent project db restore --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
