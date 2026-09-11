# `workflow plugin list`

Syntax: `cutagent workflow plugin list`

## Search terms

- list workflow plugins
- installed workflow integrations
- user plugin folders
- system plugin folders
- workflow plugin inventory

## What it does

List installed custom add-ons.

## Preflight and readback

Before execution, know that both scopes are inspected. Afterward, use `workflow plugin info` and `validate` on relevant paths and verify loading inside DaVinci Resolve.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Only immediate directories are returned; files are ignored.
- Results are sorted within each root, user scope first.
- Global dry-run has no special behavior; this remains the same local read.
- An empty list proves only that no visible immediate plugin directories were found in those two roots.

## Examples

- `cutagent workflow plugin list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
