# `version prune`

Syntax: `cutagent version prune --session-id VALUE`

## Search terms

- prune session checkpoints
- delete checkpoint history
- checkpoint garbage collection
- deleted CutAgent session cleanup
- version.checkpoint storage cleanup

## What it does

Clean up old project checkpoints.

## Do not use when

Do not use this to remove one checkpoint, one project, or an arbitrary date range; the deletion scope is every record for the exact session id.
Do not run it before listing and inspecting all matching records and checking whether the session was truly deleted. Index removal is immediate and has no undo.

## Preflight and readback

After execution, check pruned/remaining/deleted/skipped counts and bytes; list both the removed and retained session ids; verify shared snapshots remain; investigate any skipped count; and remember that removed index metadata cannot be reconstructed from the command result.

## Public arguments and options

- `--session-id` (required) — CutAgent session id whose checkpoints should be removed

## Boundaries and gotchas

- Exact help is `cutagent version prune --session-id SESSION`.
- `--session-id` is syntactically required.
- Matching is exact and case-sensitive.
- All matching records are removed; there is no per-checkpoint confirmation or `--force`.
- The output does not identify which checkpoint ids or paths were removed/skipped.
- Global dry-run is a genuine early return and performs no index read, match count, path safety check, or deletion.
- Dry-run does not trim or validate session id.

## Examples

- `cutagent version prune --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
