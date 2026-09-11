# `fairlight group assign`

Syntax: `cutagent fairlight group assign [GROUP] [--track VALUE]`

## Search terms

- assign track to Fairlight group
- group audio tracks together
- link dialogue tracks
- add track to edit group
- create Fairlight track group
- put A1 in group
- unassign audio track from group
- set Fairlight group membership
- link mixer controls across tracks
- create dialogue edit group
- change Fairlight group link options
- batch control grouped tracks

## What it does

Check Fairlight track group availability.

## Do not use when

Use the DaVinci Resolve Fairlight UI to create/delete a track group, assign or unassign tracks, and configure which controls are linked. If the real request is an independent per-track change rather than persistent group membership, use the specific supported command such as `fairlight track mute`, `fairlight track solo`, `fairlight track lock`, `fairlight track rename`, or the appropriate track-level gain/pan operation. Do not substitute `fairlight vca assign`: it is a separate VCA concept and is also unsupported.

## Public arguments and options

- `GROUP` (optional) — Track group name
- `--track/-t` (optional) — Audio track index

## Boundaries and gotchas

- The command does not inspect the current project or timeline.
- Passing one of those labels here does not make it an existing or assignable group.
- Studio does not change this command's hardcoded outcome.
- The suggested workaround is descriptive only.
- CutAgent CLI does not open the Fairlight page, focus the Group controls, or automate the manual UI.
- The command cannot unassign a track either.
- Empty group names, omitted group names, or invented names do not act as a “remove from group” convention.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight group assign --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
