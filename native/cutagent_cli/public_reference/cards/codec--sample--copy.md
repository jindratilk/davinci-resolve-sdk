# `codec sample copy`

Syntax: `cutagent codec sample copy NAME DEST [--overwrite]`

## Search terms

- copy codec SDK example
- get x264 encoder sample
- copy DaVinci Resolve CodecPlugin source
- start from official codec example
- obtain IOPlugin Makefile and headers

## What it does

Copy a codec example.

## Do not use when

Use `codec scaffold` only when the two-file placeholder is sufficient; use this command when real SDK headers, wrappers, Makefiles, and project files are needed. Use `developer examples-list codec` to discover available files when no exact sample name is known. Use `codec build` after copying, `codec package` after producing a bundle, and `codec install` only for a built plugin—not for the raw sample tree. Do not use the x264 sample as a promise that x264 itself or its headers/libraries are installed.

## Preflight and readback

Before copying, run `developer sdk-doctor` and confirm `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/CodecPlugin` exists; dry-run the chosen alias/path and inspect the resolved source and destination.

## Public arguments and options

- `NAME` (required) — Sample name or relative path
- `DEST` (required) — Destination path
- `--overwrite` (optional, default: `false`) — Replace an existing destination

## Examples

- `cutagent codec sample copy --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
