# `auto-edit run`

Syntax: `cutagent auto-edit run PATH [--doctor] [--fail-fast]`

## Search terms

- run an auto-edit recipe
- execute deterministic YAML edit workflow
- apply several CutAgent operations from one file
- rerun a repeatable editing pipeline
- run recipe with diagnostics first
- fail fast multi-step edit
- orchestrate fixed DaVinci Resolve edits from YAML

## What it does

Create an automatic edit.

## Do not use when

Use `auto-edit silence-cut`, `auto-edit podcast-edit`, or `auto-edit podcast-multicam` when the request is one of those purpose-built workflows; they build their own plans instead of consuming recipe YAML. Use `batch validate` when the task is only to check recipe structure. Use individual commands when the next action depends on inspecting the preceding result, because recipe dispatch cannot branch on step output and is not transactional.

## Preflight and readback

Run `batch validate` and inspect the normalized operation names, targets, external input/output paths, and ordering. Run this command with global `--dry-run` to see the normalized steps, then repeat with `--doctor` if DaVinci Resolve and media-tool readiness matter.

## Public arguments and options

- `PATH` (required) — Path to deterministic recipe YAML
- `--doctor` (optional, default: `false`) — Run doctor preflight before steps
- `--fail-fast/--continue-on-error` (optional, default: `true`) — Stop on first step failure

## Boundaries and gotchas

- `--continue-on-error` can compound partial state because later steps run against whatever earlier steps left behind.
- `--doctor` failure stops before step zero regardless of recipe contents.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent auto-edit run --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
