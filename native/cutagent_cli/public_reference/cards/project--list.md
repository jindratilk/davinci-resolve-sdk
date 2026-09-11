# `project list`

Syntax: `cutagent project list`

## Search terms

- list DaVinci Resolve projects
- find project by name
- current project library folder contents
- which project is open
- check project exists
- project library inventory

## What it does

List all projects in the current project folder.

## Do not use when

Do not use the display index as input to `project open`, delete, or rename: those commands identify projects by name. Do not use it to inspect the current project's settings, timelines, or media; use `project info`, `timeline list`, or media readbacks. Do not infer that a project is safely disposable from a name alone; use `project cleanup-scratch` for its guarded scratch-project rules.

## Preflight and readback

Run before `project open`, project import/create, or any name-targeted project operation to capture exact spelling and detect collisions in the current folder. After `project create`, import, delete, or rename, rerun it and verify the expected name and current marker.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Duplicate-looking names can exist in different folders; this command cannot expose those other-folder matches.
- On a very large folder the full machine response is large; use global output selection only when it preserves the exact name needed for the next command.

## Examples

- `cutagent project list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
