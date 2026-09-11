# `color group rename`

Syntax: `cutagent color group rename GROUP NEW_NAME`

## Search terms

- rename Color group
- change grading group name
- relabel pre-clip post-clip group
- rename shared grade group
- fix Color group naming
- preserve members under new group name

## What it does

Rename a color group.

## Do not use when

Use `color group add` to create a separate group, `color group assign` to move membership, and node label commands to rename nodes. Do not use rename as a merge: changing to another group's name is not a supported way to combine graphs or memberships.

## Preflight and readback

List groups and query members under the old name. After the real rename, list groups, query the new name and compare member unique IDs plus both stage graph counts; confirm the old name now fails so downstream workflows/configuration are updated.

## Public arguments and options

- `GROUP` (required) — Color group name
- `NEW_NAME` (required) — New color group name

## Boundaries and gotchas

- The command-specific dry-run is genuinely non-mutating and does not connect to DaVinci Resolve, but therefore it also does not prove the old group exists or the new name is acceptable.

## Examples

- `cutagent color group rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
