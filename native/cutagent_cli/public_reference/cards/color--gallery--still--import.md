# `color gallery still import`

Syntax: `cutagent color gallery still import PATH [--album VALUE]`

## Search terms

- import DRX into gallery
- add still image to Color album
- load grade file as gallery still
- bring saved look into project gallery
- import still into named album
- add external gallery grade

## What it does

Import still(s) into selected album.

## Do not use when

Use `gallery still apply` after import when the grade should affect a clip, `color grade-apply` to apply a DRX directly without adding it to the Gallery, and `gallery still grab` to capture the current timeline frame plus grade.

## Preflight and readback

List the target album and record its count, verify the file type/content, then dry-run with an explicit `--album`. If image representation matters, separately test PNG/JPG export because a DRX-only import may have no captured still image.

## Public arguments and options

- `PATH` (required) — Still image or DRX path
- `--album` (optional) — Album name or 1-based index

## Boundaries and gotchas

- Duplicate grades/labels are not detected.
- Omitted `--album` uses mutable current Gallery selection, which album creation/switch can change independently of timeline context.

## Examples

- `cutagent color gallery still import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
