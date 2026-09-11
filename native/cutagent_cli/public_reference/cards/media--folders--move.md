# `media folders move`

Syntax: `cutagent media folders move PATH TARGET_PATH`

## Search terms

- move Media Pool bin
- relocate folder subtree
- reorganize bins
- move nested bin to another parent
- change Media Pool folder parent
- transfer bin hierarchy
- move folder under target bin

## What it does

Move a media pool folder.

## Do not use when

Use `media move NAME TARGET` to move one Media Pool item rather than a folder. Use `media folders create` if the destination path does not yet exist; move refuses missing segments. Use a rename command when the parent should remain unchanged. Do not move a parent into itself or one of its descendants; the command has no explicit cycle preflight and delegates rejection to DaVinci Resolve.

## Preflight and readback

Capture the complete source subtree and destination counts with `media folders tree`, confirm the destination exists and is not within the source, and dry-run the exact pair of paths. If current folder was inside the moved subtree, explicitly reopen a known path before current-scoped work.

## Public arguments and options

- `PATH` (required) — Folder path to move
- `TARGET_PATH` (required) — Target folder path

## Boundaries and gotchas

- Source and destination must already exist.
- The command does not capture or restore current folder.
- Moving a Media Pool folder does not move source files on disk and should not alter linked timeline record positions, but dependent name-only automation may resolve differently after hierarchy changes.

## Examples

- `cutagent media folders move --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
