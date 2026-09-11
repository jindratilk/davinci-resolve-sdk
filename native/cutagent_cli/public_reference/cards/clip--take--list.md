# `clip take list`

Syntax: `cutagent clip take list [NAME]`

## Search terms

- list alternate takes on clip
- inspect take stack
- see which take is selected
- count timeline clip takes
- show alternate Media Pool sources
- verify take add or delete
- inspect DaVinci Resolve take selector

## What it does

List takes on a clip.

## Do not use when

Use `clip info`/`source-range` when only the currently active source/timeline range is needed; take list exposes alternatives, not full current-item properties. Use Media Pool listing to discover candidate media before adding a take. Do not treat takes as camera angles in a multicam clip or as versioned Color grades; those have separate containers and commands.

## Preflight and readback

Run it before every take mutation and retain the selected index plus media/range rows. If a take selection changed the timeline item's visible name, target the readback by the newly selected media name or by current item rather than assuming the old name still resolves.

## Public arguments and options

- `NAME` (optional)

## Examples

- `cutagent clip take list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
