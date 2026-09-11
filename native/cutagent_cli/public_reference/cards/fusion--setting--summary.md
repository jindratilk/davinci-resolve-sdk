# `fusion setting summary`

Syntax: `cutagent fusion setting summary PATH [--connections] [--animated]`

## Search terms

- summarize Fusion setting
- quick setting graph summary
- setting animated inputs
- dead Fusion tools
- unused animation tools
- setting MediaOut summary
- Fusion layout summary
- compact .setting report
- Saver MediaOut summary
- setting validity count
- SourceOp graph summary

## What it does

Summarize a Fusion template graph.

## Do not use when

Do not use this compact command when source line ranges, per-tool positions, complete warnings/errors, or detailed tool rows are needed. Use `fusion setting inspect`.
Do not use it as a pass/fail gate.
Do not expect `--connections` to include full per-tool metadata; it adds edge rows and dead-tool names only.
Do not expect `--animated` to list every numeric input. It includes only inputs whose SourceOp resolves to BezierSpline or PolyPath.
Do not use dry-run for a different preview.

## Preflight and readback

Use an explicit clip selector when exporting from DaVinci Resolve.
Enable `--connections` when topology matters and `--animated` when reviewing keyframe/path dependencies. Without them, only counts are returned for those categories.
Summary is orientation, not execution proof.
No cleanup is needed because the command is read-only. Manage only the source artifact according to the export workflow that created it.

## Public arguments and options

- `PATH` (required) — .setting file to summarize
- `--connections` (optional, default: `false`) — Include SourceOp connection edges
- `--animated` (optional, default: `false`) — Include animated input references

## Boundaries and gotchas

- `--connections` and `--animated` are independent boolean options.
- Error and warning details are not included in summary; only counts and layout details remain.
- Missing or duplicate ViewInfo makes layout unhealthy but does not necessarily make `valid` false.
- It does not report rendered text values, hashes, tool input values, or pixel evidence.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion setting summary --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
