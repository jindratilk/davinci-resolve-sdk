# `project db create`

Syntax: `cutagent project db create NAME --dir VALUE`

## Search terms

- project db create
- Create a project storage location.
- project db create help
- project db create command

## What it does

Create a project storage location.

## Do not use when

Do not use this to create a project inside an existing library, or for PostgreSQL/network/cloud libraries.

## Preflight and readback

Run dry-run and inspect the normalized target and collision checks.

## Public arguments and options

- `NAME` (required) — Database name
- `--dir` (required) — Database directory path

## Boundaries and gotchas

- `--dir` is required and the final target must not exist.

## Examples

- `cutagent project db create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
