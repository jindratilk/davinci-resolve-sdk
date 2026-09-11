# `asset artifact-index`

Syntax: `cutagent asset artifact-index [--root VALUE] [--limit VALUE]`

## Search terms

- find latest generated artifact
- recent verification frames
- locate exported setting file
- list preview renders
- newest CutAgent output files
- find contact sheet
- artifact folder inventory
- proof image path for visual check
- recent JSON or Markdown artifacts

## What it does

List recent exports.

## Do not use when

Do not use newest mtime alone as proof that an artifact belongs to the current command run; constrain roots and compare the expected path/name/run context.

## Preflight and readback

Pass narrow run-specific roots and a small limit. Then inspect/validate the selected artifact with the appropriate visual or file-format tool; for mutation proof also run DaVinci Resolve state/readback checks.

## Public arguments and options

- `--root` (optional, repeatable, default: `["artifacts"]`) — Artifact root directory; repeatable
- `--limit` (optional, default: `80`) — Maximum rows to return; <=0 means all

## Boundaries and gotchas

- `--limit 0` or a negative value means unlimited.

## Examples

- `cutagent asset artifact-index --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
