# `fusion template assets list`

Syntax: `cutagent fusion template assets list TEMPLATE`

## Search terms

- list Fusion template assets
- template-adjacent assets
- Fusion asset folder
- template assets inventory
- list template files
- hidden Fusion assets
- asset path discovery

## What it does

List template-adjacent assets.

## Do not use when

Do not use this command as recursive inventory. Nested asset files are omitted.
Do not use it to prove file type, readability, integrity, dependency references, safety, or whether DaVinci Resolve will load an asset.
Do not assume an empty list means the template exists or has no referenced external dependencies.
Do not expect dry-run to perform less work.
Do not expose the inventory without reviewing hidden filenames and sensitive local paths.

## Preflight and readback

Before execution, identify the exact template path and independently confirm whether it exists.
Check nested directories separately when relevant.
Listing reports only path/name.

## Public arguments and options

- `TEMPLATE` (required) — Template path

## Boundaries and gotchas

- The command does not filter extensions or filenames.
- It does not parse the template to determine which assets are actually referenced.

## Examples

- `cutagent fusion template assets list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
