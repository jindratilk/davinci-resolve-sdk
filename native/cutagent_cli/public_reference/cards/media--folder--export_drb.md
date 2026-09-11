# `media folder export-drb`

Syntax: `cutagent media folder export-drb FOLDER FILE`

## Search terms

- export Media Pool folder DRB
- save bin as .drb
- archive Media Pool folder structure
- create DaVinci Resolve bin file
- export project media bin
- back up Media Pool organization
- transfer folder to another project

## What it does

Export a media pool folder file.

## Do not use when

Use metadata export for CSV data rather than portable bin structure.

## Preflight and readback

After export, require file existence/size, then import into an isolated disposable folder/project and compare the full resulting tree before trusting scope. Treat unexpected project-wide content as sensitive and delete the archive when no longer needed.

## Public arguments and options

- `FOLDER` (required) — Media Pool folder path to export
- `FILE` (required) — Output .drb file

## Boundaries and gotchas

- Do not expose/share it based only on the requested folder name.
- The command does not create parent directories and returns no checksum, object count, or overwrite/cleanup handle.

## Examples

- `cutagent media folder export-drb --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
