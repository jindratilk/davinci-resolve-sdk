# `color gallery album create`

Syntax: `cutagent color gallery album create [NAME]`

## Search terms

- create gallery still album
- add Color page album
- make folder for grabbed stills
- organize grades in new still collection
- create project gallery bin
- add named still album

## What it does

Create a gallery still album.

## Do not use when

Use `color power-grade album create` for a cross-project PowerGrade album, `gallery album rename` for an existing album, and `gallery still import` when the album already exists and the task is to add content. Do not create a new album merely to switch to an existing same-named album; duplicate-name prevention is not implemented.

## Preflight and readback

List albums and record the current album before creation. Use an explicit unique name and dry-run to validate nonblank input. Then explicitly switch back if the prior album must remain current.

## Public arguments and options

- `NAME` (optional) — Optional album name

## Boundaries and gotchas

- The dry-run placeholder is not a prediction of the actual default name.
- There is no duplicate-name check and no ordinary-album delete command in this command family.
- Accidental test albums cannot be cleaned up through the matching CLI surface.

## Examples

- `cutagent color gallery album create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
