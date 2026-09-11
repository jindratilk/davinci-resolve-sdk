# `media matte delete`

Syntax: `cutagent media matte delete CLIP PATHS...`

## Search terms

- delete clip matte
- remove matte association from Media Pool clip
- detach external alpha matte
- remove left or right eye matte
- clear selected matte paths
- unlink matte PNG from clip
- clean up clip mattes
- delete multiple matte references

## What it does

Delete mattes from a media pool clip.

## Do not use when

Use `media matte list` first to obtain exact attached paths. Use timeline-matte management for timeline mattes; clip-matte deletion does not target the folder-level timeline-matte collection.

## Preflight and readback

Checkpoint if the matte is hard to recreate. After deletion, rerun `media matte list` and verify unrelated paths remain; independently confirm the matte file still exists or remove it separately only when authorized.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `PATHS` (required, repeatable) — Matte paths to delete

## Boundaries and gotchas

- At least one path is required by the CLI.
- The command cannot target by eye, index, basename, or all-mattes shorthand.

## Examples

- `cutagent media matte delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
