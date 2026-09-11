# `project cleanup-scratch`

Syntax: `cutagent project cleanup-scratch [--prefix VALUE] [--force] [--include-current] [--limit VALUE]`

## Search terms

- delete CutAgent scratch projects
- preview test project cleanup
- scratch project prefixes
- protect current project
- project deletion safety limit
- include current scratch project

## What it does

Clean up DaVinci Resolve scratch projects.

## Do not use when

Do not use broad/custom prefixes unless every matching project is disposable. Matching is simple `startswith`, not a tag or exact-name contract.
Do not use `--include-current` unless closing and permanently deleting the active scratch project is explicitly intended.
Do not use this for normal user projects. Default prefixes are product test conventions, not proof that content is safe to delete.
Do not raise `--limit` merely to bypass a safety refusal; inspect the complete candidate list and narrow prefixes first.
Do not assume `--force` plus global dry-run deletes anything.

## Preflight and readback

Review every candidate's name, matched prefix, and current flag, plus every skipped row. Require candidate count within a deliberately small limit.
If the current project was included, confirm it closed safely and the Project Manager is in the expected folder/context.

## Public arguments and options

- `--prefix` (optional, repeatable) — Scratch project name prefix to match; repeat for multiple. Defaults to known CutAgent scratch prefixes.
- `--force/-f` (optional, default: `false`) — Actually delete matched scratch projects. Without --force this command only previews.
- `--include-current` (optional, default: `false`) — Allow deleting the currently open project if it matches a scratch prefix.
- `--limit` (optional, default: `25`) — Maximum matched projects allowed before cleanup refuses to run.

## Boundaries and gotchas

- Supplying any `--prefix` replaces the defaults rather than adding to them.
- Matching is case-sensitive and uses the first matching prefix in option order.
- `--limit` defaults to 25 and must be at least 1.
- The limit counts candidates after the current project has been skipped unless `--include-current` is set.
- No `--force` means preview, even without `--dry-run`.
- Global dry-run also previews even when `--force` is supplied.
- `--include-current` alone does not delete; it only changes candidacy.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent project cleanup-scratch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
