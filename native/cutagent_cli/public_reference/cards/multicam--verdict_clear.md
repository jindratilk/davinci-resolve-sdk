# `multicam verdict-clear`

Syntax: `cutagent multicam verdict-clear --rule-id VALUE [--registry-path VALUE]`

## Search terms

- remove multicam UI verdict
- delete manual verdict rule
- multicam rule ID removal
- verdict registry cleanup
- remove stale UI evidence
- manual multicam registry
- isolated verdict clear

## What it does

Remove a multicam review note.

## Do not use when

Do not target a label, clip name, regex, or angle count; removal is by exact stable rule ID only.
Do not assume a successful exit means a rule existed. Missing IDs are an idempotent success with `removed:false`, and the registry is still rewritten.
Do not use the repository default for experiments. Supply an isolated `--registry-path`.

## Preflight and readback

Before execution, run `multicam verdict-list`, capture the complete rule being removed, confirm its exact ID and why its evidence is obsolete, and preserve any required historical record.
Use global dry-run with the same ID/path to verify command targeting. Note that dry-run does not prove the ID exists.
If `removed:false`, recheck the resolved path and exact case-sensitive ID rather than assuming deletion occurred.

## Public arguments and options

- `--rule-id` (required) — Rule id returned by multicam verdict-list or multicam inspect
- `--registry-path` (optional) — Optional manual UI verdict registry path

## Boundaries and gotchas

- IDs are matched as exact case-sensitive strings.
- All entries sharing the ID are removed, despite set replacing only the first matching entry.
- Dry-run checks only nonblank ID and does not open the registry.
- There is no `--force` or interactive confirmation.

## Examples

- `cutagent multicam verdict-clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
