# `color version delete`

Syntax: `cutagent color version delete NAME [--remote] [--clip VALUE] [--force]`

## Search terms

- delete color version
- remove grade version
- delete local grade take
- remove remote color version
- clean up duplicate color versions
- erase named Color page version
- remove alternate grade
- delete all versions with same name
- discard grade variation
- remove active color version safely
- clean old grading version
- delete clip color take

## What it does

Delete a color version.

## Do not use when

Use `color version add`/`duplicate` to preserve the current grade as another named version before discarding work. Use `color reset` when the goal is to clear a clip's current grade while retaining its version structure. Use Gallery still/DRX export when a grade must be archived outside this clip before removal.
Do not use this command to delete only one occurrence of a duplicated name: there is no ID or occurrence selector, and it deliberately removes all exact matches in that type. Rename/reconstruct unique versions first if any duplicate must survive. Do not omit `--remote` for a remote target merely because the same name exists locally; without it the local namespace is modified. For source-linked remote grade workflows across repeated media instances, inspect with `color source-grade plan` before deleting shared remote state.

## Preflight and readback

Count exact-name occurrences separately for local and remote, record the current version name/type, and export/checkpoint any grade that may be needed later. Ensure another differently named version exists in the requested namespace if the target is active.
Inspect or render the surviving grade because name-list verification proves deletion, not visual equivalence. Save the project explicitly only after confirming the resulting active grade and version inventory.

## Public arguments and options

- `NAME` (required) — Version name
- `--remote` (optional, default: `false`)
- `--clip` (optional)
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Global `--dry-run` is unsafe for this command.
- In JSON/machine mode, deletion is rejected unless `--force`/`-f` is present.
- `--dry-run` does not waive this requirement.
- There is no option to delete one duplicate.
- The only active version in a namespace cannot be deleted.
- The command compares names exactly and does not strip or normalize `name` or `--clip`.
- `--remote` selects a separate type ID; a local and remote `Version 1` can coexist.
- However, it does not render or compare the remaining grade.
- Partial deletion is possible if one iteration succeeds and a later duplicate deletion fails.
- Do not infer the actual route from that metadata alone.
- The command does not save the project.
- Deletion may remain only in the current unsaved project state until the user saves.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent color version delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
