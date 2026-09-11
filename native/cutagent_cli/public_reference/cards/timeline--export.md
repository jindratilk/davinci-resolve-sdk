# `timeline export`

Syntax: `cutagent timeline export PATH [--format VALUE]`

## Search terms

- export current timeline
- timeline EDL export
- timeline FCPXML export
- timeline AAF export
- timeline OTIO export
- timeline DRT export
- export interchange file
- timeline XML alias

## What it does

Export the current timeline.

## Do not use when

This command exports a timeline interchange/transfer artifact only.
Do not rely on `--dry-run` for safety.
The command does not preflight or preserve an existing destination.

## Preflight and readback

The CLI success message alone does not verify the artifact on disk.

## Public arguments and options

- `PATH` (required) — Output path
- `--format` (optional, default: `"edl"`) — Export format: edl, fcpxml, aaf, otio, drt

## Boundaries and gotchas

- Exact help is `cutagent timeline export PATH --format FORMAT`.
- The command does not expand `~`, resolve relative paths, canonicalize the destination, or append an extension.
- It does not require the path extension to match `--format`.
- It does not create parent directories.
- It does not preflight writability or available disk space.
- It does not check whether the destination already exists.
- Success output is only `Exported timeline to: PATH`.
- There is no command-level dry-run branch.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
