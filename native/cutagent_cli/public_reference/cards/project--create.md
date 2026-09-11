# `project create`

Syntax: `cutagent project create NAME [--media-location VALUE]`

## Search terms

- create new DaVinci Resolve project
- make empty project
- start fresh editing project
- create and open project
- new test project
- new project with media location
- initialize DaVinci Resolve project
- avoid modifying existing project

## What it does

Create a new project.

## Do not use when

Do not use `project create` when the intended project already exists; use `project open`. Do not use it to make a copy of the current project; use the appropriate project export/import, archive/restore, or duplicate workflow so media/settings/history semantics are explicit. Do not create a throwaway project with an ambiguous human name and later delete by guess; use a unique scratch/test name and verify it with `project list`/`status`.

## Public arguments and options

- `NAME` (required) — Project name
- `--media-location` (optional) — Optional project media location path

## Boundaries and gotchas

- The command does not save the previously open project or preserve its active timeline context for later restoration.
- It does not prove a timeline, media storage layout, or custom project settings because none are created by this command.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent project create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
