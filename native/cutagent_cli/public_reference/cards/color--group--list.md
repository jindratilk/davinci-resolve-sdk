# `color group list`

Syntax: `cutagent color group list`

## Search terms

- list Color groups
- show project grading groups
- find shared color group names
- inspect pre-clip post-clip groups
- enumerate DaVinci Resolve color groups
- check whether Color group exists
- get group index and name

## What it does

List project color groups.

## Preflight and readback

Run before add/rename/delete to resolve the exact current spelling and after the mutation to verify presence, absence or the new name. For assignment workflows, follow list with group clips; the existence of a group says nothing about whether any clip belongs to it.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command does not show clip count, graph stages, node count, shared-node contents, or which timeline contains members.

## Examples

- `cutagent color group list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
