# `project archive`

Syntax: `cutagent project archive NAME PATH [--force]`

## Search terms

- archive DaVinci Resolve project
- create DRA archive
- project media archive
- force archive modal
- dry-run project archive
- archive artifact verification

## What it does

Archive a project to disk.

## Do not use when

Verify the actual nonempty archive artifact and test restoration into a safe target.

## Preflight and readback

Use an absolute path with an existing parent.
Record its absolute path, size/content inventory, timestamp, and hashable contents where practical.

## Public arguments and options

- `NAME` (required) — Project name
- `PATH` (required) — Archive path (directory)
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Only the parent must exist; the target itself need not exist.
- Unlike project export, archive does not separately accept the current open project's name as existence proof.
- Name comparison is exact and case-sensitive.
- Artifact verification does not inspect archive completeness or restorability.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project archive --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
