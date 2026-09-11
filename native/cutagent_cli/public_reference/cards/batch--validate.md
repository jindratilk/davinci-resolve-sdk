# `batch validate`

Syntax: `cutagent batch validate PATH`

## Search terms

- validate CutAgent YAML recipe
- check batch edit file syntax
- lint deterministic edit recipe
- verify recipe version and operations
- inspect normalized batch steps
- catch unsupported recipe fields
- list supported recipe operations

## What it does

Check an edit plan.

## Do not use when

Use `batch run` (normally after this command) to actually dispatch the recipe.

## Public arguments and options

- `PATH` (required) — Path to deterministic recipe YAML

## Boundaries and gotchas

- The only accepted recipe version is numeric YAML `1`.
- The file must exist and decode as UTF-8.
- The root must be an object and `steps` must be a nonempty list.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent batch validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
