# `project folders up`

Syntax: `cutagent project folders up`

## Search terms

- go to parent project folder
- GotoParentFolder
- Project Manager parent navigation
- leave current project folder
- already at root warning
- project library navigation

## What it does

Open to parent folder.

## Do not use when

Do not expect global dry-run to avoid navigation.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no local options; `--force` is invalid.
- Mutation enforcement is invoked without a dry-run-specific `mutating` flag.
- This makes global dry-run potentially state-changing despite dry-run metadata.
- Missing/proxy errors are handled only by the outer command wrapper.
- One invocation attempts only one parent step.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project folders up --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
