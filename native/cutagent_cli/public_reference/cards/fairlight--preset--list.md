# `fairlight preset list`

Syntax: `cutagent fairlight preset list`

## Search terms

- list Fairlight presets
- show available audio presets
- find saved Fairlight presets
- what Fairlight presets can I apply
- enumerate timeline audio presets
- check preset names before apply
- discover Fairlight mix presets
- get Resolve Fairlight preset list
- verify Dialogue Cleaner preset exists
- list reusable audio configurations
- check whether preset apply is ready

## What it does

List available Fairlight presets.

## Do not use when

This list command never changes a timeline.
Do not use this result as an inventory of Equalizer presets, dynamics presets, Fairlight FX/plug-in presets, system audio templates, render presets, or files in DaVinci Resolve's preset directories.
Do not use dry-run to answer which presets exist.

## Preflight and readback

No timeline selection, save, checkpoint, or page switch is needed because the method is project-independent and non-mutating.
After the read, no project verification is required.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not require an active timeline.
- The CLI does not sort alphabetically, remove duplicates, normalize whitespace/case, or attach preset types.
- The output contains no preset contents, version, source path, compatibility, modified date, scope, or applied-state metadata.
- The command does not switch to the Fairlight page, open any preset panel, or refresh GUI libraries.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight preset list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
