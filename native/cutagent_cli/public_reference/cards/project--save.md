# `project save`

Syntax: `cutagent project save`

## Search terms

- save current DaVinci Resolve project
- persist project changes
- safe save dry-run
- current project persistence
- project settings write
- pending manual verification
- project manager placeholder rejection

## What it does

Save the current project.

## Preflight and readback

Export or archive a recoverable artifact for high-risk work.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--force` is invalid.
- The command does not close/reopen or otherwise prove durable persistence; perform that readback explicitly when required.

## Examples

- `cutagent project save --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
