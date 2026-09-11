# `media folders delete`

Syntax: `cutagent media folders delete PATH [--force]`

## Search terms

- delete Media Pool bin
- remove empty folder from Media Pool
- delete nested bin tree
- purge folder hierarchy
- remove project bin
- delete folder and subfolders
- clean up disposable Media Pool bins

## What it does

Delete a media pool folder.

## Do not use when

Use `media delete` for one Media Pool item while retaining its bin. Use `media folders move` when the subtree should survive under another parent. Avoid deleting a nonempty bin until every contained item and timeline dependency has been inventoried; the command offers no keep-contents or reparent-children mode.

## Preflight and readback

Use `media folders tree` and `media list --recursive` from the target to inventory all child folders, clips, timelines, and source paths. Create a project/version checkpoint when contents matter, then use dry-run and, in machine mode, explicit `--force`.

## Public arguments and options

- `PATH` (required) — Folder path to delete
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Project deletion does not remove source files from disk.
- Path matching is exact and case-sensitive, root-relative, and accepts `/` or `>` separators.

## Examples

- `cutagent media folders delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
