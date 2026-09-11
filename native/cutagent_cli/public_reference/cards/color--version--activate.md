# `color version activate`

Syntax: `cutagent color version activate NAME [--remote] [--clip VALUE]`

## Search terms

- activate color version
- switch grade version
- load named grade
- make local version current
- change active Color page version
- switch clip to alternate grade
- choose version by name
- activate remote version
- restore named color look
- load Color page take
- set current grade version

## What it does

Activate a color version.

## Do not use when

Use `color version duplicate` or `add` when a new version is required; activate only loads an existing name. Use `color version list` first when name/type is uncertain. Use `color version delete` to remove a version. Use `color source-grade prepare-remote` when a named Remote Version must be created/loaded consistently across every same-source instance, not just one resolved timeline item.

## Preflight and readback

Before running, identify the exact timeline item, list both local and remote versions, record current name/type, and check for duplicate names across the two namespaces. Use the correct `--remote` flag; a visible identical name does not identify its type.
Check page, timeline and playhead restoration.

## Public arguments and options

- `NAME` (required) — Version name
- `--remote` (optional, default: `false`)
- `--clip` (optional)

## Boundaries and gotchas

- Name-only readback is insufficient.
- Version activation changes grade context but does not save the project explicitly, render a frame, compare pixels or expose the version's node contents.
- The target is current item or name only, with no track/record-frame selector.
- Duplicate clip names need external disambiguation.

## Examples

- `cutagent color version activate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
