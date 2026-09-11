# `color group remove`

Syntax: `cutagent color group remove [--clip VALUE]`

## Search terms

- remove clip from Color group
- ungroup timeline clip from grade
- stop clip inheriting group corrections
- detach shot from shared color group
- make clip ungrouped
- remove pre-clip post-clip processing
- clear clip Color group membership

## What it does

Remove a clip from its color group.

## Do not use when

Use `color group delete` when the entire group and shared graphs should be removed, `color group assign` to move the item directly into another group, and local grade reset commands when local clip nodes—not membership—should be cleared. Removing membership does not copy the shared group look into the clip before detaching.

## Preflight and readback

Inspect the clip's current group and record the group's member unique IDs plus a rendered frame. Remove using an explicit clip name.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Omitting `--clip` uses current-item/playhead resolution and can silently target the wrong timeline item.

## Examples

- `cutagent color group remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
