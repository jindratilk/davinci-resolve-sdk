# `media folders create`

Syntax: `cutagent media folders create PATH`

## Search terms

- create Media Pool bin
- add nested bins
- make folder hierarchy
- organize project media folders
- create bin path under Master
- add subfolder to Media Pool
- ensure Media Pool folder exists
- create dailies bin structure

## What it does

Create a folder (including nested).

## Do not use when

Use `media folders open` when the path already exists and the goal is only navigation. Use `media move` to place clips in a bin and `media folders move` to relocate an existing subtree.

## Preflight and readback

Capture the relevant parent in `media folders tree`, normalize the intended root-relative path, and dry-run the exact string when user input may contain whitespace or separators.

## Public arguments and options

- `PATH` (required) — Folder path (e.g., 'A/B/C')

## Boundaries and gotchas

- Root-name matching and all child-name matching are case-sensitive.

## Examples

- `cutagent media folders create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
