# `script env print`

Syntax: `cutagent script env print`

## Search terms

- DaVinci Resolve scripting environment
- PYTHONPATH diagnostics
- DaVinci Resolve script roots
- Fusion Scripts folder
- Developer Scripting Modules
- local SDK path diagnostics

## What it does

Check DaVinci Resolve setup diagnostics.

## Do not use when

Do not publish its output without reviewing local paths; environment values can reveal workstation layout.
Do not expect it to diagnose every platform or installation layout.
Do not expect dry-run to hide or simulate values; it returns the same current-process diagnostics.

## Preflight and readback

Compare the reported values with the exact shell/process that launches CutAgent CLI, not with a different terminal session.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not connect to DaVinci Resolve and does not require a project or timeline.
- Each root reports only string path and `exists`.
- It does not check whether DaVinci Resolve external scripting is enabled.
- It does not report embedded-bridge status.
- It does not modify/export variables for the calling shell.

## Examples

- `cutagent script env print --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
