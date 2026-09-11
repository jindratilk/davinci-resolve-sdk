# `project open`

Syntax: `cutagent project open NAME`

## Search terms

- open DaVinci Resolve project
- switch current project
- open existing project name
- project open readback
- current folder project
- wait for project state
- already open project
- Project Manager context

## What it does

Open an existing project.

## Do not use when

Do not switch away from a project with unsaved work. This command has no confirmation or save step.
Do not use blank/whitespace names; no static trimming/nonblank validation is performed.

## Public arguments and options

- `NAME` (required) — Project name

## Boundaries and gotchas

- There is no `--force` or confirmation.
- The command connects before dry-run.
- Verification compares exact/case-sensitive names.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project open --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
