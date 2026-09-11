# `media folders open`

Syntax: `cutagent media folders open PATH`

## Search terms

- open Media Pool bin
- navigate to nested folder
- set current Media Pool folder
- enter bin by path
- browse a specific Media Pool folder
- change current bin for import
- open Master child folder

## What it does

Navigate to a folder.

## Do not use when

Use `media folders create` if any path segment should be created. Use `media folders tree` when locating a folder without changing UI/current state. Do not use an ambiguous shorthand when duplicate names exist at different depths; provide the complete root-relative path.

## Preflight and readback

Restore the prior bin after current-scoped work.

## Public arguments and options

- `PATH` (required) — Folder path to navigate to

## Boundaries and gotchas

- Folder-name matching is exact and case-sensitive.
- Opening a folder changes implicit behavior of later commands: `media import` destination, `media list` scope, and duplicate-name preference can all change even though no project content was edited.

## Examples

- `cutagent media folders open --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
