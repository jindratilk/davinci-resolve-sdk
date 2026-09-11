# `project folders open`

Syntax: `cutagent project folders open NAME`

## Search terms

- navigate Project Manager folder
- current project folder
- project library child folder
- folder open dry-run
- verify current folder name
- folder path context

## What it does

Open to a folder.

## Do not use when

Do not pass a multi-level path and expect recursive traversal.

## Preflight and readback

Use `up` or `root` to restore the prior navigation state when needed.

## Public arguments and options

- `NAME` (required) — Folder name

## Boundaries and gotchas

- There is no `--force` or confirmation.
- The command connects before dry-run.
- Dry-run existence uses exact/case-sensitive string membership in the current child-folder list.
- Verification is set only if current folder exactly equals the requested string.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`
- `VALIDATION_ERROR`

## Examples

- `cutagent project folders open --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
