# `fusion setting inspect`

Syntax: `cutagent fusion setting inspect PATH`

## Search terms

- inspect Fusion setting
- parse .setting graph
- list setting tools
- setting SourceOp connections
- missing MediaOut
- dead Fusion tools
- unused animation tools
- Fusion flow layout
- missing ViewInfo
- duplicate node positions
- Saver MediaOut export
- setting structural validity

## What it does

Inspect a Fusion template graph.

## Do not use when

A structurally invalid graph is returned as successful inspection data.
Do not use `--dry-run` expecting a different plan.
Do not use it to repair a graph or layout. Inspection is read-only; import-time layout repair belongs to other setting workflows.

## Preflight and readback

Prefer exporting the intended composition from DaVinci Resolve with an explicit clip selector and comp index so GUI selection cannot redirect the readback.
Static inspection cannot prove importability or visible output.
Preserve or delete the inspected artifact according to the workflow that created it.

## Public arguments and options

- `PATH` (required) — .setting file to inspect

## Boundaries and gotchas

- BezierSpline, PolyPath, and StyledTextCLS do not require ViewInfo and are excluded from flow-tool counts.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion setting inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
