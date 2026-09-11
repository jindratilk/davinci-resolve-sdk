# `media folders root`

Syntax: `cutagent media folders root`

## Search terms

- go to Media Pool root
- open Master bin
- reset current Media Pool folder
- navigate back to top bin
- leave nested Media Pool folder
- make media commands target Master

## What it does

Open to root folder.

## Do not use when

Use `media folders open PATH` when the next operation should target a known non-root bin. Use `media folders tree` when the task is only to inspect the hierarchy; tree always starts at root without changing current folder. Do not use this to move items to Master—use `media move` or `media folders move` for content or folder relocation.

## Preflight and readback

Reopen the saved path after the workflow if the user's Media Pool navigation state should be preserved.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Changing it can alter where `media import` places assets and which duplicate name is preferred by name-only mutations.

## Examples

- `cutagent media folders root --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
