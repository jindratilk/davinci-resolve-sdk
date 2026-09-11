# `project info`

Syntax: `cutagent project info`

## Search terms

- current DaVinci Resolve project info
- project open status
- Project Manager placeholder
- current timeline FPS
- project timeline count
- project settings summary
- current project folder
- timeline resolution info
- project context detection

## What it does

Read current project information.

## Do not use when

Do not use this for the complete project setting map; use `project settings`.
Do not assume missing fields mean false/zero.
Do not infer a real open project from a nonempty project name alone; the embedded bridge can expose a Project Manager placeholder that this command specially detects.

## Preflight and readback

Before execution, ensure DaVinci Resolve and embedded bridge are connected. No project needs to be open.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--settings` is invalid.
- Current folder/path are included only in placeholder output, not real-project output.
- Global dry-run has no special branch and performs the same reads.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
