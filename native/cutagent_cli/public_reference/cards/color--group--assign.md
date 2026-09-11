# `color group assign`

Syntax: `cutagent color group assign GROUP_NAME [--clip VALUE]`

## Search terms

- assign clip to Color group
- add shot to grading group
- make clip inherit group grade
- put timeline item in pre-clip post-clip group
- share color correction across clips
- group a timeline clip for grading
- move clip into Color group

## What it does

Assign a clip to a color group.

## Do not use when

Use `color group add` if the group does not yet exist, `color group remove` to make the clip ungrouped, and `color grade-copy`/`color source-remote-cdl` when the desired relation is copied or remote-source grading rather than group pre/post processing. Use clip links for edit synchronization; Color-group membership is a grading relationship only.

## Preflight and readback

Check same-named media instances separately because resolution selects a timeline item, not a media-pool master.

## Public arguments and options

- `GROUP_NAME` (required) — Color group name
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The group must already exist with an exact case-sensitive name.
- Omitting `--clip` uses mutable current-item/playhead context.
- The response is only a success message; there is no built-in membership readback, previous-group report, or render verification.
- It does not automatically assign other occurrences of the same source media.

## Examples

- `cutagent color group assign --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
