# `media timeline-matte list`

Syntax: `cutagent media timeline-matte list FOLDER`

## Search terms

- list timeline mattes in folder
- inspect Media Pool timeline matte collection
- count timeline matte items
- verify timeline matte import
- show folder-level mattes
- find timeline matte proxies
- audit timeline mattes by bin

## What it does

List timeline mattes in a media pool folder.

## Do not use when

Use `media matte list CLIP` for mattes attached to one clip; that command returned actual paths. Use `storage matte timeline-add` to add timeline matte files.

## Preflight and readback

Capture the target folder's baseline count, add/import a known timeline matte while that folder is current, then list the explicit folder path and compare count. Retain the add command's returned item names/paths externally because this list cannot recover them. Verify the matte in DaVinci Resolve UI/render when identity or visual correctness matters.

## Public arguments and options

- `FOLDER` (required) — Media Pool folder path

## Boundaries and gotchas

- The command resolves from root; it does not depend on or change current folder.

## Examples

- `cutagent media timeline-matte list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
