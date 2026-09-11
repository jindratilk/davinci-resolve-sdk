# `fairlight group list`

Syntax: `cutagent fairlight group list [--limit VALUE]`

## Search terms

- list Fairlight groups
- inspect audio track groups
- show linked Fairlight tracks
- find dialogue edit group
- list mixer groups
- inspect Group 1 through Group 99
- check whether audio tracks are grouped
- diagnose Fairlight link groups
- inspect group label pool
- audit Fairlight group state

## What it does

Runs the public `fairlight group list` CutAgent command.

## Do not use when

Use `fairlight vca list` when the user means VCA labels rather than edit/mix groups, `fairlight tracks` or `timeline track items audio` for audio-track/item inventory, and the DaVinci Resolve Fairlight UI when authoritative membership, link options, group creation, or assignment is required.

## Preflight and readback

No post-mutation verification is needed because the command is read-only.

## Public arguments and options

- `--limit` (optional, default: `50`)

## Boundaries and gotchas

- The offset is diagnostic and must not be treated as a stable group identifier.
- Cloud, PostgreSQL, or inaccessible project-library storage cannot use this route, and path inference can fail even though DaVinci Resolve has an active project.
- `--dry-run` is different: it returns the intended tables and scope without connecting to DaVinci Resolve or reading actual state.

## Examples

- `cutagent fairlight group list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
