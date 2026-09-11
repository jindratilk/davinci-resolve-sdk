# `color power-grade list`

Syntax: `cutagent color power-grade list [--db]`

## Search terms

- list available PowerGrades
- show saved reusable grades
- find PowerGrade by label
- inspect PowerGrade albums and stills
- get PowerGrade selector index
- enumerate User Gallery grades
- find source version for PowerGrade apply
- check which PowerGrades exist
- browse PowerGrade library
- map PowerGrade albums to still labels
- preflight a PowerGrade application

## What it does

List power grades.

## Do not use when

Use the DaVinci Resolve Gallery UI to confirm empty PowerGrade albums, since neither output has a row for an empty container. Use `color gallery album list` or `color gallery still list` for ordinary non-PowerGrade Gallery content.

## Preflight and readback

After listing, handle an empty array as a valid “no stills” state, not a command failure.

## Public arguments and options

- `--db` (optional, default: `false`) — List PowerGrade stills from the user gallery database

## Boundaries and gotchas

- Dict key identities/order are discarded in favor of value iteration; only label and generated indexes survive.
- It does not join/return PowerGrade album ownership, so duplicate labels cannot be disambiguated by album in this view.
- The command has no special dry-run branch.
- Duplicate labels and blank labels are allowed in outputs.
- A current project is required in both modes, but no timeline is needed.

## Examples

- `cutagent color power-grade list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
