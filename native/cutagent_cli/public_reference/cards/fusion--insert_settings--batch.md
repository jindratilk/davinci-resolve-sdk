# `fusion insert-settings batch`

Syntax: `cutagent fusion insert-settings batch [--spec VALUE] [--spec-json VALUE]`

## Search terms

- batch Text+ holders
- JSON setting insertion spec
- multiple Fusion overlays
- precise batch holder placement
- batch setting templates
- partial batch failure
- batch dry-run mutation
- render setting per item
- spec-json Fusion holders
- multi-item setting import
- batch timeline graphics

## What it does

Insert multiple Fusion and Text+ clips from templates.

## Do not use when

Do not use global `--dry-run` as a safety boundary.
Do not use it on a user timeline without an explicit checkpoint, item-by-item reviewed spec, empty target ranges, and a cleanup plan.
Do not expect atomic behavior. Earlier successful items remain inserted when a later item fails.
Use numeric seconds such as `2`.
Do not expect text/image substitutions to be required or confirmed. A provided value is silently ineffective when its recognized placeholder is absent.

## Preflight and readback

Before execution, confirm the active project/timeline, timeline start frame, fps, track count, and occupancy of every target interval. Prefer a newly created scratch timeline for first use.
Validate the JSON shape and inspect every source template. Confirm placeholders, MediaOut, node layout, fonts/media/plugins, numeric duration seconds, holder kind, track, and record-domain `at`.
Do not run global dry-run on a valuable timeline. If testing dry-run semantics, use a disposable timeline and assume it will mutate.
After execution, branch on counts and inspect each `created[]` and `failures[]` entry. List every target track, export each inserted composition by unique clip name, inspect its graph, and export in-range frames.
Cleanup must be explicit. Delete successful holders or, preferably for an isolated run, switch back to the original timeline and delete the entire uniquely named scratch timeline.

## Public arguments and options

- `--spec` (optional) — Path to JSON spec file
- `--spec-json` (optional) — Inline JSON spec

## Boundaries and gotchas

- `--spec` and `--spec-json` are mutually exclusive and exactly one is required.
- `placeholders` must be a JSON object; arrays and scalars fail that item.
- The output’s nested layout cleanup does not disclose this outer temporary deletion.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion insert-settings batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
