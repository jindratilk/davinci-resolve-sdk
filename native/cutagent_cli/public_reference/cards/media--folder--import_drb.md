# `media folder import-drb`

Syntax: `cutagent media folder import-drb FILE [--source-clips-path VALUE]`

## Search terms

- import Media Pool folder DRB
- restore bin archive
- load .drb into current folder
- import DaVinci Resolve folder file
- bring bin structure into project
- restore Media Pool organization
- import DRB with source clips path
- transfer archived bins

## What it does

Import a media pool folder file.

## Do not use when

Do not import an untrusted or uninspected DRB into a production root: archive scope can be broader than its export target and duplicate names are allowed. Use an isolated destination folder/project first.

## Preflight and readback

Inspect the DRB origin and create/open a dedicated empty destination folder. Move accepted content out and delete the isolated wrapper or restore current folder as appropriate.

## Public arguments and options

- `FILE` (required) — DRB/folder file
- `--source-clips-path` (optional) — Source clips path

## Boundaries and gotchas

- Duplicate direct folder names are allowed.

## Examples

- `cutagent media folder import-drb --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
