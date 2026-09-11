# `media relink`

Syntax: `cutagent media relink NAME PATH`

## Search terms

- reconnect missing source media
- point clip to media folder
- locate original audio file
- fix missing media path
- reconnect source file after move
- relink clip by filename

## What it does

Relink clip to a media path.

## Do not use when

Use `media replace` when intentionally changing the item to a different source identity/filename. Use `media import` when no Media Pool object exists. Use proxy/full-resolution link commands for proxy-specific associations.

## Preflight and readback

Prefer a concrete file path because CutAgent CLI then checks exact path readback. After relink, require `media info` Online status and File Path plus timeline item ID/path/timing readback.

## Public arguments and options

- `NAME` (required) — Clip name
- `PATH` (required) — New media path

## Boundaries and gotchas

- Path existence/type is validated before connecting, including in dry-run.
- Exact-name/current-folder duplicate rules apply.
- Same-source duplicate objects must each be relinked if independently unlinked.

## Examples

- `cutagent media relink --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
