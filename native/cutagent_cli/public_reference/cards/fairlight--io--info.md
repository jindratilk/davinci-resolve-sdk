# `fairlight io info`

Syntax: `cutagent fairlight io info [--limit VALUE]`

## Search terms

- inspect Fairlight patch I/O setup
- list VTR input settings
- list VTR output settings
- diagnose capture audio configuration
- inspect tape input output setup
- check whether patch setup rows exist
- investigate Fairlight hardware routing evidence

## What it does

Read stored Fairlight patch I and O setup rows from the DaVinci Resolve project.

## Do not use when

Use DaVinci Resolve's Patch Input/Output dialog and OS/audio-interface tools for authoritative present hardware and routing.

## Preflight and readback

Corroborate any hardware/routing interpretation in the DaVinci Resolve dialog because this command is read-only historical/project-state evidence. No post-mutation verification is needed.

## Public arguments and options

- `--limit` (optional, default: `20`)

## Boundaries and gotchas

- The command resolves only local Disk project storage.

## Examples

- `cutagent fairlight io info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
