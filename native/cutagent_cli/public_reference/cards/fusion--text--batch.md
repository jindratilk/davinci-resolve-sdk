# `fusion text batch`

Syntax: `cutagent fusion text batch --batch VALUE`

## Search terms

- batch Fusion text updates
- TextPlus JSON batch
- Fusion text center batch
- partial text batch failure
- inverse Fusion text batch
- batch clip selector
- TextPlus position reset
- verify Fusion text batch

## What it does

Update text in Fusion templates.

## Do not use when

Do not use this when all rows must be atomic. Successful earlier entries remain changed if a later entry fails.
It only builds plans and marked an intentionally missing clip successful because no selector/tool/input resolution occurred.
Do not rely on `tool` as a strict target. If the explicit name is missing, text-tool selection can fall back to another candidate-scored Text+ node.

## Preflight and readback

Before execution, validate the JSON structure and inventory every target timeline item, Fusion composition, tool/input, original text, center, and item position.
Run dry-run and review normalized/clean text, role candidates, input fallbacks, center/position plans, and row count. Treat all dry-run rows as unverified plans.
For center/position rows, compare requested values with readback/property results.
Independently query actual tool inputs and render representative output.

## Public arguments and options

- `--batch/--input` (required) — Batch JSON path

## Boundaries and gotchas

- `--batch TEXT` and `--input TEXT` are aliases and one is required.
- Dry-run does not validate paired track/record selectors, clip existence, composition presence, tool names, input IDs, center support, or timeline-item properties.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion text batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
