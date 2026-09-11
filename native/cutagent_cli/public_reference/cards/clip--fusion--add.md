# `clip fusion add`

Syntax: `cutagent clip fusion add [NAME] [--track VALUE] [--record-frame VALUE]`

## Search terms

- add Fusion composition to clip
- create Fusion comp on timeline item
- start node graph for clip
- attach another Fusion composition
- make empty Fusion page on shot
- add MediaIn MediaOut graph
- create alternate Fusion comp

## What it does

Add a new Fusion composition to a clip.

## Do not use when

Use `clip fusion tool-set` to change an input in an existing graph. Do not add a second comp merely to add another node: identify the intended comp and edit its graph instead. Use `timeline fusion-clip` operations when creating a standalone Fusion clip rather than attaching a comp to source media.

## Preflight and readback

Resolve the exact occurrence and run `clip fusion list`; preserve the existing index/name rows because add provides no readback. Add only in a disposable or backed-up timeline if the graph is not yet designed. Save explicitly after graph construction; this command itself does not report a project save.

## Public arguments and options

- `NAME` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- Test the actual media/item type and DaVinci Resolve edition; do not infer support from command discovery alone.

## Examples

- `cutagent clip fusion add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
