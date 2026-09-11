# `timeline insert-generator`

Syntax: `cutagent timeline insert-generator NAME [--fusion] [--ofx]`

## Search terms

- timeline insert-generator
- Insert a generator into the timeline at the playhead.
- timeline insert-generator help
- timeline insert-generator command

## What it does

Insert a generator into the timeline at the playhead.

## Do not use when

Do not use this command when placement track, duration, start/end, or destination layer must be specified explicitly. Those choices are delegated to current DaVinci Resolve timeline state.
Do not pass both `--fusion` and `--ofx`.
The generator may already exist even though the command returned failure, so inspect the timeline first.

## Preflight and readback

Before execution, checkpoint the project; inspect the active timeline, playhead, target/enabled/locked video tracks, surrounding items, and the exact generator name available in the selected standard/Fusion/OFX catalog.
Use dry-run to confirm the displayed name and one selected mode.
After execution, inspect returned asset/method/clip/track/bounds fields, re-enumerate the timeline, and verify exactly one new generator at the intended placement. Open its Inspector/Fusion/OFX controls and export a proof frame to confirm rendered pixels.

## Public arguments and options

- `NAME` (required) — Generator name
- `--fusion` (optional, default: `false`) — Insert a Fusion generator
- `--ofx` (optional, default: `false`) — Insert an OFX generator

## Boundaries and gotchas

- `--fusion` selects Fusion generator mode.
- `--ofx` selects OFX generator mode.
- An active timeline is required.
- Dry-run checks mode with Fusion precedence and returns before the mutual-exclusion validation.
- Therefore `--fusion --ofx --dry-run` currently succeeds and claims Fusion mode.
- Matching uses only summary fields that are both present and readable on a candidate.
- At least one comparable field is required for a match.
- It does not verify generator Inspector parameters, Fusion/OFX graph, actual pixels, audio, or overlaps.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline insert-generator --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
