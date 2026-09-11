# `fusion tool registry`

Syntax: `cutagent fusion tool registry [--query VALUE] [--category VALUE] [--limit VALUE]`

## Search terms

- Fusion available tools
- Fusion creation IDs
- installed Fusion effects
- Fusion registry categories

## What it does

List available Fusion node creation IDs from the live registry.

## Do not use when

Use fusion tool list to inspect nodes already present in the current composition. Do not assume registry presence proves edition entitlement or successful rendering.

## Preflight and readback

This command does not change the composition.

## Public arguments and options

- `--query/-q` (optional) — Filter by creation ID, name, or category
- `--category` (optional) — Filter by registry category
- `--limit` (optional, default: `1024`) — Maximum tools to return

## Examples

- `cutagent fusion tool registry --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
