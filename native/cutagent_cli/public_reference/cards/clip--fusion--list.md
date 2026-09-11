# `clip fusion list`

Syntax: `cutagent clip fusion list [NAME] [--track VALUE] [--record-frame VALUE]`

## Search terms

- list Fusion compositions on clip
- show clip Fusion comps
- count compositions attached to timeline item
- find Fusion composition indexes
- inspect alternate Fusion comps
- does this clip have Fusion
- enumerate Fusion pages for clip

## What it does

List Fusion compositions on a clip.

## Do not use when

Use `clip fusion tools` when the question is which nodes are inside a known composition. Use `clip fusion by-name` when an agent must resolve a human name or stable numeric alias into an index, but do not assume its reported name agrees with this command. Use `timeline fusion-composition list` for the timeline-owned composition surface rather than a named source-backed clip. This command cannot tell which composition is currently loaded and cannot validate the rendered result.

## Preflight and readback

Run the list before any add/import/delete to retain the exact count and index ordering. After mutation, list again, compare the complete rows, then inspect the intended index with `clip fusion tools` and Viewer/render evidence.

## Public arguments and options

- `NAME` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Do not feed a list name blindly into `by-name` or `load`.
- By contrast, `tools --comp 1` on that same clip raises an out-of-range validation error.
- `--at` is an alias for `--record-frame` and is record-domain, not clip-local.

## Examples

- `cutagent clip fusion list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
