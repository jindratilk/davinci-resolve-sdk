# `text list-presets`

Syntax: `cutagent text list-presets`

## Search terms

- list text presets
- discover Text+ templates
- known Fusion titles
- static title catalog
- list setting templates
- built-in text titles
- non-exhaustive preset list
- caption template discovery

## What it does

List known text presets and visible template title templates.

## Do not use when

DaVinci Resolve exposes no exhaustive scriptable Fusion-title list through this route.
Do not assume a static built-in catalog entry is installed or works in the active DaVinci Resolve version.

## Preflight and readback

Remember that the default is `~/resolve-templates`, not the complete DaVinci Resolve Effects Library hierarchy.
For GUI-only or missing presets, obtain the exact installed name from the active system rather than inventing one.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The operation is read-only and has no special dry-run branch.
- Static catalog membership does not prove installation.
- It does not parse or validate listed templates.
- Duplicate filenames across different directories are not deduplicated.

## Examples

- `cutagent text list-presets --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
