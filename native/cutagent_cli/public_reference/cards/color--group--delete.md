# `color group delete`

Syntax: `cutagent color group delete GROUP_NAME [--force]`

## Search terms

- delete Color group
- remove shared grading group
- destroy pre-clip post-clip graph
- ungroup all clips and delete group
- clean up project color groups
- remove DaVinci Resolve Color group
- permanently discard group grade

## What it does

Delete a color group.

## Do not use when

Do not delete as a shortcut for disabling a shared look unless permanently losing the group graph is intended.

## Preflight and readback

List the exact group, export/document both pre/post graph contents with the available node tools, enumerate member unique IDs, and render representatives. In JSON/machine mode include `--force`. After deletion, require the group absent from list, inspect every former member for null membership and retained local grade, and render again. Save the project only after confirming the intended visual result.

## Public arguments and options

- `GROUP_NAME` (required) — Color group name
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- JSON/machine mode refuses deletion without `--force`.
- Member clip survival does not preserve the shared grade.
- The success response is not a readback; it does not report former members, deleted node counts, or project-save status.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent color group delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
