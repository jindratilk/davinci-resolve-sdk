# `fusion image batch`

Syntax: `cutagent fusion image batch --batch VALUE`

## Search terms

- batch Fusion image injection
- Fusion image JSON batch
- partial Fusion batch failure
- image batch visual verification
- MediaID batch assignment
- group input image batch
- restore Fusion image source

## What it does

Update images in Fusion templates.

## Do not use when

Do not run a broad batch without a per-entry source/target inventory and a restoration plan. The command is non-transactional: earlier entries remain changed when a later entry fails.
Do not rely on dry-run to prove that a clip exists or a Fusion composition contains suitable tools.
Do not use HTML, missing paths, directories, or ambiguous files.
Do not use this command when every entry must succeed atomically, when exact visual equivalence is required without frame/render proof, or when the target graph should be manipulated by explicit low-level tool commands instead.

## Preflight and readback

Before execution, inspect the current timeline, uniquely identify every target clip or track/record-frame point, and list each target composition's tools. Record original source paths/Media IDs where possible.
Export a representative before-frame for visual comparison and retain the original media source needed to restore the graph.
Then export representative frames or renders and inspect them visually.
If any entry fails or visual output is wrong, restore successful earlier entries explicitly.

## Public arguments and options

- `--batch/--input` (required) — Batch JSON path

## Boundaries and gotchas

- `--batch TEXT` and `--input TEXT` are aliases; one is required.
- Dry-run builds selectors without resolving them against the current timeline.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion image batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
