# `media folders list`

Syntax: `cutagent media folders list`

## Search terms

- list bins in current Media Pool folder
- show immediate subfolders
- browse child bins
- inspect current bin hierarchy
- find nested Media Pool folder
- enumerate folders under Master
- check whether bin exists here

## What it does

List subfolders in the current folder.

## Do not use when

Use `media folders tree` for full root-to-leaf paths, clip counts, and recursive hierarchy. Use `media list` to inspect clips/timelines inside the current folder. Use `media folders open` when the task is navigation rather than discovery. Do not assume an empty result means the Media Pool has no bins; it means only that the current folder has no direct children.

## Preflight and readback

When duplicate folder names exist at different depths, retain parent context from `media folders tree` rather than relying on this name-only response.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Scope is entirely determined by persistent current-folder state.
- Only direct child names are returned.

## Examples

- `cutagent media folders list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
