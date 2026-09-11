# `media folders tree`

Syntax: `cutagent media folders tree`

## Search terms

- show complete Media Pool tree
- inspect all bins recursively
- map Media Pool folder hierarchy
- find folder full path
- count clips per bin
- locate nested bin
- audit Media Pool structure
- list all subfolders from Master

## What it does

Check the complete folder tree.

## Do not use when

Use `media folders list` for a lightweight immediate-child query after current folder is known. Use `media list --recursive` or `media search` when item identities and source paths matter; tree returns only per-folder counts.

## Preflight and readback

Run tree before folder creation, movement, or deletion to capture canonical paths and direct counts. After the mutation, rerun and compare the source parent, destination parent, moved/deleted subtree, and counts. Keep the complete root-inclusive path for commands that otherwise face duplicate folder names.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Tree ignores current folder and always begins at root, so it cannot prove `folders open` or `folders root` changed current navigation.

## Examples

- `cutagent media folders tree --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
