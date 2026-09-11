# `timeline list`

Syntax: `cutagent timeline list`

## Search terms

- list timelines in project
- find sequence by name
- which timeline is current
- enumerate project timelines
- check timeline exists
- compare timeline frame rates
- active sequence list

## What it does

List all timelines in the current project.

## Do not use when

Do not use `timeline list` to inspect clips, tracks beyond fps, resolution, duration, or playhead; use `timeline info`, `timeline items`, or track readbacks. Do not treat an index as permanent; `timeline switch --index` can use the current index, but name is safer after any create/delete/reorder. Do not use it to list timelines in another project; open the intended project first. Do not use the UI fields as frame-level proof of timeline contents; they only establish that DaVinci Resolve's window is visually reachable/not blocked.

## Preflight and readback

Run before `timeline switch`, delete, rename, duplicate, or name-targeted operations to capture exact names and current index. After create/delete/rename/duplicate, rerun and compare row count/names.

## Public arguments and options

This command has no command-specific arguments or options.

## Examples

- `cutagent timeline list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
