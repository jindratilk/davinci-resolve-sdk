# `timeline duplicate`

Syntax: `cutagent timeline duplicate NEW_NAME [--source VALUE]`

## Search terms

- duplicate timeline
- copy sequence
- clone current edit
- make timeline version copy
- duplicate named timeline
- preserve edit before changes
- create alternate timeline from existing
- copy timeline without changing original

## What it does

Runs the public `timeline duplicate` CutAgent command.

## Do not use when

Do not use it to create an empty timeline (`timeline create`) or copy a project (`project export`/import/archive workflow). Do not substitute manual item copying, XML, or EDL for this route when Fusion graphs, markers, timing, or track structure must survive.

## Preflight and readback

List timelines, confirm the exact source/current edit, and dry-run the intended unique name. If the command fails, inspect timeline/dependency cleanup and recoverability before retrying.

## Public arguments and options

- `NEW_NAME` (required) — New timeline name
- `--source` (optional) — Optional source timeline name

## Boundaries and gotchas

- The requested target name must be non-empty and absent before mutation; the DRT route rechecks collision before renaming the import.

## Examples

- `cutagent timeline duplicate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
