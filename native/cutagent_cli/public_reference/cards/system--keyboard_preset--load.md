# `system keyboard-preset load`

Syntax: `cutagent system keyboard-preset load NAME`

## Search terms

- system keyboard-preset load
- Load an exact keyboard preset.
- system keyboard-preset load help
- system keyboard-preset load command

## What it does

Load an exact keyboard preset.

## Do not use when

Do not normalize or guess a preset name. Do not use this command to import a preset file or edit individual shortcut assignments.

## Public arguments and options

- `NAME` (required) — Exact preset name

## Boundaries and gotchas

- The operation changes application-global keyboard state and does not require an open project.

## Examples

- `cutagent system keyboard-preset load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
